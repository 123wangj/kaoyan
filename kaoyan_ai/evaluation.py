from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from kaoyan_ai.schemas import AgentResponse, AgentRunTrace, Intent
from kaoyan_ai.validators import validate_agent_response


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    message: str
    expected_intents: tuple[Intent, ...]
    required_terms: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()


DEFAULT_CASES = (
    EvaluationCase(
        "compound_weakness_plan",
        "分析我的薄弱点并制定七天复习计划",
        (Intent.PERSONAL_ANALYSIS, Intent.STUDY_PLAN),
        required_terms=("计划",),
    ),
    EvaluationCase(
        "grounded_solution",
        "解释操作系统中页表和快表的区别",
        (Intent.SOLVE_QUESTION,),
        required_terms=("页表",),
    ),
    EvaluationCase(
        "safe_admission",
        "预测目标院校明年的录取分数",
        (Intent.ADMISSION_PREDICTION,),
        required_terms=("仅供参考",),
    ),
)


def score_response(case: EvaluationCase, response: AgentResponse) -> dict[str, Any]:
    answer = response.answer or ""
    required_hits = sum(term in answer for term in case.required_terms)
    forbidden_hits = sum(term in answer for term in case.forbidden_terms)
    validation = validate_agent_response(response)
    term_score = required_hits / max(len(case.required_terms), 1)
    score = 0.55 * validation.confidence + 0.45 * term_score
    if forbidden_hits:
        score *= 0.5
    return {
        "case": case.name,
        "score": round(score, 3),
        "validation": validation.__dict__,
        "required_hits": required_hits,
        "forbidden_hits": forbidden_hits,
    }


def load_traces(paths: Iterable[Path]) -> list[AgentRunTrace]:
    traces: list[AgentRunTrace] = []
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                traces.append(AgentRunTrace.model_validate_json(line))
            except Exception:
                continue
    return traces


def trace_metrics(traces: Iterable[AgentRunTrace]) -> dict[str, Any]:
    rows = list(traces)
    if not rows:
        return {"runs": 0, "success_rate": 0.0, "average_confidence": 0.0}
    successful = sum(trace.status == "completed" for trace in rows)
    tool_calls = sum(len(trace.tool_results) for trace in rows)
    failed_tools = sum(
        not result.success for trace in rows for result in trace.tool_results
    )
    return {
        "runs": len(rows),
        "success_rate": round(successful / len(rows), 3),
        "average_confidence": round(
            sum(trace.confidence for trace in rows) / len(rows),
            3,
        ),
        "tool_calls": tool_calls,
        "tool_failure_rate": round(failed_tools / max(tool_calls, 1), 3),
        "average_iterations": round(
            sum(trace.iteration_count for trace in rows) / len(rows),
            2,
        ),
    }
