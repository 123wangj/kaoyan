from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from kaoyan_ai.schemas import AgentResponse, Intent


@dataclass
class ValidationResult:
    valid: bool
    confidence: float
    issues: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def validate_agent_response(response: AgentResponse) -> ValidationResult:
    """Cheap deterministic checks before an answer leaves the runtime."""

    issues: list[str] = []
    answer = (response.answer or "").strip()
    if len(answer) < 12:
        issues.append("answer_too_short")
    if "大模型服务暂时不可用" in answer or "离线占位结果" in answer:
        issues.append("model_unavailable")
    if response.intent in {Intent.SOLVE_QUESTION, Intent.RECITATION}:
        if response.citations:
            cited_ids = {item.id for item in response.citations}
            if len(cited_ids) != len(response.citations):
                issues.append("duplicate_evidence")
        elif "暂无本地召回资料" not in answer:
            issues.append("no_retrieval_evidence")
    if response.intent == Intent.ADMISSION_PREDICTION:
        has_disclaimer = bool(re.search(r"仅供参考|不确定|数据不足|置信", answer))
        if not has_disclaimer:
            issues.append("prediction_without_uncertainty")
    if response.intent == Intent.SIMILAR_TRAINING:
        if "答案" not in answer:
            issues.append("generated_questions_without_answers")
        if "解析" not in answer:
            issues.append("generated_questions_without_explanations")
    confidence = max(0.05, 1.0 - 0.18 * len(issues))
    if "model_unavailable" in issues:
        confidence = min(confidence, 0.2)
    blocking = {
        "answer_too_short",
        "prediction_without_uncertainty",
        "generated_questions_without_answers",
        "generated_questions_without_explanations",
    }
    return ValidationResult(
        valid=not any(item in blocking for item in issues),
        confidence=round(confidence, 3),
        issues=issues,
        metrics={"answer_chars": len(answer), "citation_count": len(response.citations)},
    )


def validate_study_plan(plan: dict[str, Any]) -> ValidationResult:
    issues: list[str] = []
    tasks = [
        task
        for week in plan.get("weekly", [])
        for task in week.get("tasks", [])
    ]
    if not tasks:
        issues.append("no_executable_tasks")
    ids = [str(task.get("id") or "") for task in tasks]
    if len(ids) != len(set(ids)):
        issues.append("duplicate_task_ids")
    if any(not task.get("scheduled_date") for task in tasks):
        issues.append("missing_schedule")
    if any(int(task.get("estimated_minutes") or 0) <= 0 for task in tasks):
        issues.append("invalid_duration")
    confidence = max(0.0, 1.0 - len(issues) * 0.25)
    return ValidationResult(not issues, confidence, issues, {"task_count": len(tasks)})
