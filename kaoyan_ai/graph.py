from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from kaoyan_ai.agents import (
    AdmissionPredictionAgent,
    DailyPushAgent,
    IntentAgent,
    PersonalAnalysisAgent,
    RecitationAgent,
    SimilarTrainingAgent,
    SolutionAgent,
    StudyPlanAgent,
)
from kaoyan_ai.config import get_settings
from kaoyan_ai.chat_policy import classify_chat_scope, out_of_scope_response
from kaoyan_ai.agent_runtime import AgentRuntime
from kaoyan_ai.schemas import AgentRequest, AgentResponse, AgentState, Intent
from kaoyan_ai.tools import build_default_registry


class ConversationMemory:
    """基于文件的对话记忆管理，为每个用户维护最近 N 轮对话历史。

    对话历史保存在 data_dir/chat_history/{user_id}.jsonl 中，
    每行是一条 {"role": "user"|"assistant", "content": "..."} 记录。
    所有写操作使用 atomic write（先写 .tmp 再 os.replace），
    避免并发读取看到半写状态。
    """

    def __init__(self, max_turns: int = 10) -> None:
        self.max_turns = max_turns
        self._lock = threading.RLock()

    @property
    def _dir(self) -> Path:
        return get_settings().data_dir / "chat_history"

    def _path(self, user_id: str) -> Path:
        safe_id = "".join(c if c.isalnum() or c in "_.-" else "_" for c in user_id) or "anonymous"
        return self._dir / f"{safe_id}.jsonl"

    def get_history(self, user_id: str) -> list[dict[str, str]]:
        """获取用户最近的对话历史。"""
        path = self._path(user_id)
        if not path.exists():
            return []
        with self._lock:
            lines = path.read_text(encoding="utf-8").strip().splitlines()
        history: list[dict[str, str]] = []
        for line in lines[-self.max_turns * 2:]:
            line = line.strip()
            if line:
                try:
                    history.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return history

    def add_turn(self, user_id: str, user_msg: str, assistant_msg: str) -> None:
        """追加一轮对话（用户提问 + AI 回答），使用 atomic write 避免并发读到半写状态。"""
        path = self._path(user_id)
        self._dir.mkdir(parents=True, exist_ok=True)
        user_record = json.dumps({"role": "user", "content": user_msg}, ensure_ascii=False)
        assistant_record = json.dumps({"role": "assistant", "content": assistant_msg}, ensure_ascii=False)
        with self._lock:
            if path.exists():
                existing = path.read_text(encoding="utf-8")
            else:
                existing = ""
            new_content = existing + user_record + "\n" + assistant_record + "\n"
            # 写入 .tmp 后 os.replace，原子替换
            tmp_path = path.with_suffix(path.suffix + ".tmp")
            tmp_path.write_text(new_content, encoding="utf-8")
            os.replace(tmp_path, path)
            self._trim(path)

    def _trim(self, path: Path) -> None:
        """保留最近 max_turns * 2 行记录，使用 atomic write。"""
        max_lines = self.max_turns * 2
        with self._lock:
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            if len(lines) > max_lines:
                lines = lines[-max_lines:]
                tmp_path = path.with_suffix(path.suffix + ".tmp")
                tmp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                os.replace(tmp_path, path)

    def clear(self, user_id: str) -> None:
        """清空某用户的对话历史(文件 + 内存),用于「新对话」。"""
        path = self._path(user_id)
        with self._lock:
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass


# 全局对话记忆实例
conversation_memory = ConversationMemory(max_turns=10)


class KaoyanTutorGraph:
    """408 辅导系统的主编排图。

    当前流程保持简单：先识别用户意图，再交给一个对应的子智能体处理。
    同时集成了对话记忆，每次请求会自动附带最近的历史上下文。
    """

    def __init__(self) -> None:
        self.intent_agent = IntentAgent()
        self.agents = {
            Intent.SOLVE_QUESTION: SolutionAgent(),
            Intent.SIMILAR_TRAINING: SimilarTrainingAgent(),
            Intent.PERSONAL_ANALYSIS: PersonalAnalysisAgent(),
            Intent.RECITATION: RecitationAgent(),
            Intent.DAILY_PUSH: DailyPushAgent(),
            Intent.ADMISSION_PREDICTION: AdmissionPredictionAgent(),
            Intent.STUDY_PLAN: StudyPlanAgent(),
        }
        self.memory = conversation_memory
        self.runtime = AgentRuntime(
            intent_agent=self.intent_agent,
            registry=build_default_registry(self.agents),
            max_iterations=get_settings().agent_max_iterations,
        )
        self._compiled = self._build_graph()

    def run(self, request: AgentRequest) -> AgentResponse:
        """运行已编译的 LangGraph；不可用时走直接调用降级路径。"""

        settings = get_settings()
        scope = classify_chat_scope(
            request.message,
            has_conversation_context=bool(request.metadata.get("conversation_history")),
            has_image=bool(request.image_base64),
        )
        if settings.chat_strict_scope and not scope.allowed:
            response = AgentResponse(
                intent=Intent.FALLBACK,
                answer=out_of_scope_response(),
                next_actions=["查看计算机考研知识图谱", "开始专业课刷题", "制定考研复习计划"],
                metadata={"scope_category": scope.category, "scope_allowed": False},
            )
        elif self._compiled is None:
            response = self._run_without_langgraph(request)
        else:
            state = self._compiled.invoke({"request": request})
            response = state["response"]

        # 记录本轮对话到记忆
        self.memory.add_turn(request.user_id, request.message, response.answer)
        return response

    def run_with_history(self, request: AgentRequest) -> AgentResponse:
        """带对话记忆的完整调用：先把历史拼入 metadata，再走正常流程。"""

        history = self.memory.get_history(request.user_id)
        if history:
            history_text = "\n".join(
                f"{'用户' if h['role'] == 'user' else 'AI'}: {h['content'][:200]}"
                for h in history[-6:]  # 最近 3 轮
            )
            request.metadata["conversation_history"] = history_text
        return self.run(request)

    def _run_without_langgraph(self, request: AgentRequest) -> AgentResponse:
        """LangGraph 未安装或编译失败时使用的降级路径。"""

        return self.runtime.run(request)

    def run_with_events(
        self,
        request: AgentRequest,
        event_sink,
        answer_chunk_sink=None,
    ) -> AgentResponse:
        """Run the same runtime while exposing planning/tool/validation events."""

        settings = get_settings()
        scope = classify_chat_scope(
            request.message,
            has_conversation_context=bool(request.metadata.get("conversation_history")),
            has_image=bool(request.image_base64),
        )
        if settings.chat_strict_scope and not scope.allowed:
            response = AgentResponse(
                intent=Intent.FALLBACK,
                answer=out_of_scope_response(),
                next_actions=["查看计算机考研知识图谱", "开始专业课刷题", "制定考研复习计划"],
                metadata={"scope_category": scope.category, "scope_allowed": False},
            )
        else:
            response = self.runtime.run(
                request,
                event_sink=event_sink,
                answer_chunk_sink=answer_chunk_sink,
            )
        self.memory.add_turn(request.user_id, request.message, response.answer)
        return response

    def _build_graph(self):
        """构建两个节点的 LangGraph 工作流。

        这里允许返回 None：即使 LangGraph 暂时不可用，测试和轻量部署也能继续运行。
        """

        try:
            from langgraph.graph import END, START, StateGraph
        except Exception:
            return None

        graph = StateGraph(AgentState)

        def plan_and_execute(state: AgentState) -> AgentState:
            state["response"] = self.runtime.run(state["request"])
            return state

        graph.add_node("agent_runtime", plan_and_execute)
        graph.add_edge(START, "agent_runtime")
        graph.add_edge("agent_runtime", END)
        return graph.compile()
