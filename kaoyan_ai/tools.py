from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from kaoyan_ai.config import get_settings
from kaoyan_ai.learning import load_learning_state, memory_review_queue, user_profile_payload
from kaoyan_ai.rag import LocalRetriever
from kaoyan_ai.schemas import (
    AgentRequest,
    AgentResponse,
    Intent,
    ToolCall,
    ToolResult,
)
from kaoyan_ai.validators import validate_study_plan


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: Callable[[dict[str, Any]], Any]
    read_only: bool = True
    requires_approval: bool = False


class ToolRegistry:
    """Explicit allow-list for every capability available to the Agent."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"duplicate tool: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "read_only": spec.read_only,
                "requires_approval": spec.requires_approval,
            }
            for spec in self._tools.values()
        ]

    def execute(self, call: ToolCall, *, approved: bool = False) -> ToolResult:
        started = time.perf_counter()
        try:
            spec = self.get(call.tool_name)
            if spec.requires_approval and not approved:
                raise PermissionError(f"tool requires approval: {call.tool_name}")
            output = spec.handler(call.arguments)
            evidence = output.citations if isinstance(output, AgentResponse) else []
            return ToolResult(
                call_id=call.id,
                tool_name=call.tool_name,
                success=True,
                output=output,
                evidence=evidence,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return ToolResult(
                call_id=call.id,
                tool_name=call.tool_name,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )


def build_default_registry(
    agents: dict[Intent, Any],
    retriever: LocalRetriever | None = None,
) -> ToolRegistry:
    retriever = retriever or LocalRetriever()
    registry = ToolRegistry()

    def search_questions(args: dict[str, Any]):
        return retriever.retrieve(
            str(args.get("query") or ""),
            collection="question_bank",
            subject=args.get("subject"),
            k=int(args.get("k") or 5),
        )

    def search_knowledge(args: dict[str, Any]):
        return retriever.retrieve(
            str(args.get("query") or ""),
            collection="knowledge_points",
            subject=args.get("subject"),
            k=int(args.get("k") or 5),
        )

    def get_learning_state(args: dict[str, Any]):
        return load_learning_state(get_settings().data_dir, str(args["user_id"]))

    def get_profile(args: dict[str, Any]):
        return user_profile_payload(
            get_settings().data_dir,
            str(args["user_id"]),
            {"total_tokens": 0, "total_requests": 0},
        )

    def get_review_queue(args: dict[str, Any]):
        state = load_learning_state(get_settings().data_dir, str(args["user_id"]))
        return memory_review_queue(state, limit=int(args.get("limit") or 8))

    def create_study_plan(args: dict[str, Any]):
        # Imported lazily to avoid coupling the reusable runtime to FastAPI at
        # module import time. The scheduler itself is deterministic and grounded
        # exclusively in the local knowledge and question stores.
        from kaoyan_ai import api

        user_id = str(args["user_id"])
        state = load_learning_state(get_settings().data_dir, user_id)
        answers = dict(args.get("answers") or {})
        answers.setdefault("duration", "1个月")
        answers.setdefault("daily_min", 90)
        answers.setdefault("focus", "四科均衡")
        plan = api._build_executable_study_plan(user_id, answers, state)
        validation = validate_study_plan(plan)
        if not validation.valid:
            raise ValueError(f"invalid study plan: {validation.issues}")
        plan["validation"] = {
            "confidence": validation.confidence,
            "issues": validation.issues,
            **validation.metrics,
        }
        api._save_study_plan(user_id, state, plan)
        return plan

    registry.register(ToolSpec("search_questions", "检索本地题库", search_questions))
    registry.register(ToolSpec("search_knowledge", "检索本地知识库", search_knowledge))
    registry.register(ToolSpec("get_learning_state", "读取用户完整学习状态", get_learning_state))
    registry.register(ToolSpec("get_user_profile", "读取用户学习画像", get_profile))
    registry.register(ToolSpec("get_review_queue", "读取间隔复习队列", get_review_queue))
    registry.register(
        ToolSpec(
            "create_study_plan",
            "根据本地知识库、题库和薄弱点生成并保存可执行学习计划",
            create_study_plan,
            read_only=False,
        )
    )

    for intent, agent in agents.items():
        name = f"delegate_{intent.value}"

        def delegate(args: dict[str, Any], selected_agent=agent):
            request = AgentRequest.model_validate(args["request"])
            return selected_agent.run(request)

        registry.register(
            ToolSpec(
                name=name,
                description=f"调用 {intent.value} 专业辅导能力",
                handler=delegate,
            )
        )
    return registry


def new_tool_call(run_id: str, step_id: str, tool_name: str, arguments: dict[str, Any]) -> ToolCall:
    return ToolCall(
        id=f"call-{uuid.uuid4().hex[:12]}",
        run_id=run_id,
        step_id=step_id,
        tool_name=tool_name,
        arguments=arguments,
    )
