from __future__ import annotations

import json
import threading
from pathlib import Path

from kaoyan_ai.agent_runtime import AgentPlanner, AgentRuntime, RunTraceStore
from kaoyan_ai.agents.intent import IntentAgent
from kaoyan_ai.agents.base import LLMClient
from kaoyan_ai.agents.solution import SolutionAgent
from kaoyan_ai.evaluation import trace_metrics
from kaoyan_ai.memory import SemanticMemory
from kaoyan_ai.rag import LocalRetriever
from kaoyan_ai.schemas import AgentRequest, AgentResponse, Intent
from kaoyan_ai.student_model import retrievability, update_knowledge_state
from kaoyan_ai.tools import ToolRegistry, ToolSpec
from kaoyan_ai.config import get_settings


def test_compound_goal_is_decomposed_in_message_order() -> None:
    old = get_settings().agent_llm_planner_enabled
    get_settings().agent_llm_planner_enabled = False
    planner = AgentPlanner(IntentAgent())
    try:
        steps = planner.plan(
            AgentRequest(
                user_id="u",
                message="先分析我的薄弱点，再制定七天学习计划并生成相似题训练",
            )
        )
    finally:
        get_settings().agent_llm_planner_enabled = old
    delegates = [step.intent for step in steps if step.tool_name.startswith("delegate_")]
    assert delegates == [
        Intent.PERSONAL_ANALYSIS,
        Intent.STUDY_PLAN,
        Intent.SIMILAR_TRAINING,
    ]
    plan_step = next(step for step in steps if step.tool_name == "create_study_plan")
    assert plan_step.tool_args["answers"]["duration"] == "1周"
    assert plan_step.tool_args["answers"]["study_days_per_week"] == 7


def test_explicit_compound_goal_skips_redundant_llm_planner(monkeypatch) -> None:
    old = get_settings().agent_llm_planner_enabled
    get_settings().agent_llm_planner_enabled = True
    planner = AgentPlanner(IntentAgent())
    monkeypatch.setattr(
        planner.llm,
        "generate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("planner should be skipped")),
    )
    try:
        steps = planner.plan(
            AgentRequest(user_id="u", message="先分析我的薄弱点，再制定七天学习计划")
        )
    finally:
        get_settings().agent_llm_planner_enabled = old
    delegates = [step.intent for step in steps if step.tool_name.startswith("delegate_")]
    assert delegates == [Intent.PERSONAL_ANALYSIS, Intent.STUDY_PLAN]


def test_ambiguous_compound_planner_disables_thinking(monkeypatch) -> None:
    old = get_settings().agent_llm_planner_enabled
    get_settings().agent_llm_planner_enabled = True
    planner = AgentPlanner(IntentAgent())
    captured = {}

    def fake_generate(*_args, **kwargs):
        captured.update(kwargs)
        return '{"intents":["solve_question"]}'

    monkeypatch.setattr(planner.llm, "generate", fake_generate)
    try:
        planner.plan(AgentRequest(user_id="u", message="这个过程然后呢？"))
    finally:
        get_settings().agent_llm_planner_enabled = old
    assert captured["enable_thinking"] is False


def test_solution_retrieves_independent_collections_concurrently() -> None:
    class ConcurrentRetriever:
        def __init__(self):
            self.barrier = threading.Barrier(2)
            self.thread_ids = set()

        def retrieve(self, *_args, **_kwargs):
            self.thread_ids.add(threading.get_ident())
            self.barrier.wait(timeout=1)
            return []

    retriever = ConcurrentRetriever()
    agent = SolutionAgent(retriever=retriever)
    agent.llm = type("OfflineLLM", (), {"generate": lambda *_args, **_kwargs: "答案"})()
    response = agent.run(AgentRequest(user_id="u", message="解释虚拟内存"))
    assert response.answer == "答案"
    assert len(retriever.thread_ids) == 2


def test_runtime_executes_tools_combines_answers_and_persists_trace(tmp_path: Path) -> None:
    old = get_settings().agent_llm_planner_enabled
    get_settings().agent_llm_planner_enabled = False
    registry = ToolRegistry()
    registry.register(ToolSpec("get_learning_state", "state", lambda _: {}))
    registry.register(ToolSpec("get_review_queue", "review", lambda _: []))
    registry.register(ToolSpec("create_study_plan", "plan", lambda _: {"schema_version": 2}))

    def delegate(args):
        request = AgentRequest.model_validate(args["request"])
        intent = (
            Intent.PERSONAL_ANALYSIS
            if "delegate_personal" in args.get("_tool", "")
            else Intent.STUDY_PLAN
        )
        return AgentResponse(intent=intent, answer=f"已完成：{request.message}")

    registry.register(
        ToolSpec(
            "delegate_personal_analysis",
            "analysis",
            lambda args: AgentResponse(
                intent=Intent.PERSONAL_ANALYSIS,
                answer="学习诊断：需要加强页面置换算法。",
            ),
        )
    )
    registry.register(
        ToolSpec(
            "delegate_study_plan",
            "plan",
            lambda args: AgentResponse(
                intent=Intent.STUDY_PLAN,
                answer="学习计划：未来七天每天完成复习和练习。",
            ),
        )
    )
    events = []
    runtime = AgentRuntime(
        intent_agent=IntentAgent(),
        registry=registry,
        memory=SemanticMemory(tmp_path),
        trace_store=RunTraceStore(tmp_path),
    )
    try:
        response = runtime.run(
            AgentRequest(user_id="alice", message="分析薄弱点并制定七天学习计划"),
            events.append,
        )
    finally:
        get_settings().agent_llm_planner_enabled = old
    assert response.metadata["compound_goal"] is True
    assert "学习诊断" in response.answer
    assert "学习计划" in response.answer
    assert any(event["type"] == "plan_created" for event in events)
    assert any(event["type"] == "validated" for event in events)
    traces = RunTraceStore(tmp_path).recent("alice")
    assert len(traces) == 1
    assert trace_metrics(traces)["tool_calls"] >= 4


def test_runtime_forwards_single_agent_model_chunks_immediately(tmp_path: Path, monkeypatch) -> None:
    old = get_settings().agent_llm_planner_enabled
    get_settings().agent_llm_planner_enabled = False
    registry = ToolRegistry()

    def fake_stream(self, *args, **kwargs):
        yield "第一段"
        yield "第二段"

    monkeypatch.setattr(LLMClient, "generate_stream", fake_stream)

    def delegate(_args):
        answer = LLMClient().generate("system", "question")
        return AgentResponse(intent=Intent.SOLVE_QUESTION, answer=answer)

    registry.register(ToolSpec("delegate_solve_question", "solution", delegate))
    runtime = AgentRuntime(
        intent_agent=IntentAgent(),
        registry=registry,
        memory=SemanticMemory(tmp_path),
        trace_store=RunTraceStore(tmp_path),
    )
    chunks = []
    try:
        response = runtime.run(
            AgentRequest(user_id="alice", message="二叉树遍历怎么做？"),
            answer_chunk_sink=chunks.append,
        )
    finally:
        get_settings().agent_llm_planner_enabled = old

    assert chunks == ["第一段", "第二段"]
    assert response.answer


def test_semantic_memory_only_extracts_explicit_facts(tmp_path: Path) -> None:
    memory = SemanticMemory(tmp_path)
    learned = memory.learn_from_request(
        "u1",
        "我的目标院校是浙江大学，每天学习90分钟，希望详细讲解",
    )
    assert len(learned) == 3
    context = memory.context("u1")
    assert "浙江大学" in context
    assert "90" in context
    assert memory.learn_from_request("u1", "这题为什么选 A") == []


def test_student_model_tracks_probability_stability_and_review() -> None:
    first = update_knowledge_state(
        None,
        is_correct=False,
        observed_at="2026-07-01T10:00:00",
        spent_seconds=20,
    )
    second = update_knowledge_state(
        first,
        is_correct=True,
        observed_at="2026-07-02T10:00:00",
        spent_seconds=70,
    )
    assert 0 < second["mastery_probability"] < 1
    assert second["stability_days"] > first["stability_days"]
    assert second["model_version"] == "bkt-fsrs-lite-v1"
    assert retrievability(second) <= 1


def test_hybrid_retriever_uses_exact_terms_and_metadata(tmp_path: Path) -> None:
    rows = [
        {
            "id": "os-tlb",
            "title": "快表 TLB",
            "content": "TLB 用于缓存页表项，加速虚拟地址转换。",
            "subject": "操作系统",
            "knowledge_points": ["快表"],
        },
        {
            "id": "cn-cache",
            "title": "网络缓存",
            "content": "HTTP 缓存可以减少重复传输。",
            "subject": "计算机网络",
            "knowledge_points": ["HTTP"],
        },
    ]
    path = tmp_path / "knowledge_points.jsonl"
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )
    results = LocalRetriever(tmp_path).retrieve(
        "操作系统快表 TLB",
        collection="knowledge_points",
        k=2,
    )
    assert results[0].id == "os-tlb"
