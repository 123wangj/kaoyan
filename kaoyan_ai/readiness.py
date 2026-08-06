from __future__ import annotations

import math
import statistics
from datetime import date, datetime, timedelta
from typing import Any


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone().replace(tzinfo=None) if parsed.tzinfo else parsed
    except (TypeError, ValueError):
        return None


def _difficulty_weight(value: object) -> float:
    text = str(value or "").strip().lower()
    if text in {"hard", "困难", "难", "3", "高级"}:
        return 1.35
    if text in {"easy", "简单", "易", "1", "基础"}:
        return 0.8
    return 1.0


def build_personal_learning_signals(
    state: dict[str, Any],
    questions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build explainable readiness signals from real learning-state events."""

    question_map = {
        str(item.get("id") or ""): item
        for item in questions
        if item.get("id")
    }
    records = [
        dict(item)
        for item in state.get("answer_records", [])
        if isinstance(item, dict)
    ]
    records.sort(
        key=lambda item: _parse_datetime(
            item.get("created_at") or item.get("timestamp")
        )
        or datetime.min
    )

    weighted_total = 0.0
    weighted_correct = 0.0
    speeds: list[float] = []
    by_question: dict[str, list[dict[str, Any]]] = {}
    now = datetime.now()
    recent_cutoff = now - timedelta(days=30)
    recent: list[dict[str, Any]] = []
    for record in records:
        question = question_map.get(str(record.get("question_id") or ""), {})
        difficulty = record.get("difficulty") or question.get("difficulty")
        weight = _difficulty_weight(difficulty)
        weighted_total += weight
        weighted_correct += weight if record.get("is_correct") else 0
        spent = record.get("spent_seconds")
        if isinstance(spent, (int, float)) and 3 <= float(spent) <= 1800:
            expected = 105.0 * weight
            speeds.append(max(0.0, min(100.0, expected / float(spent) * 100)))
        qid = str(record.get("question_id") or "")
        if qid:
            by_question.setdefault(qid, []).append(record)
        when = _parse_datetime(record.get("created_at") or record.get("timestamp"))
        if when and when >= recent_cutoff:
            recent.append(record)

    half = max(1, len(recent) // 2)
    earlier = recent[:-half]
    later = recent[-half:]

    def accuracy(rows: list[dict[str, Any]]) -> float | None:
        if not rows:
            return None
        return sum(bool(row.get("is_correct")) for row in rows) / len(rows) * 100

    first_attempts = [rows[0] for rows in by_question.values() if rows]
    repeated_latest = [rows[-1] for rows in by_question.values() if len(rows) > 1]
    recovered = [
        rows
        for rows in by_question.values()
        if len(rows) > 1
        and not rows[0].get("is_correct")
        and rows[-1].get("is_correct")
    ]
    first_accuracy = accuracy(first_attempts)
    repeat_accuracy = accuracy(repeated_latest)
    recent_earlier = accuracy(earlier)
    recent_later = accuracy(later)

    mastery_items = [
        item for item in state.get("mastery", {}).values()
        if isinstance(item, dict)
    ]
    retention_values: list[float] = []
    for item in mastery_items:
        probability = float(
            item.get("mastery_probability", float(item.get("score", 50)) / 100)
        )
        last_seen = _parse_datetime(
            item.get("last_answered_at") or item.get("last_practiced")
        )
        stability = max(0.5, float(item.get("stability_days", 1.0)))
        elapsed = max(0.0, (now - last_seen).total_seconds() / 86400) if last_seen else 0
        retention_values.append(
            max(0.0, min(1.0, probability * math.exp(-elapsed / stability))) * 100
        )

    task_rows = [
        task
        for task_set in state.get("daily_tasks", {}).values()
        if isinstance(task_set, dict)
        for task in task_set.get("tasks", [])
        if isinstance(task, dict)
    ]
    plan = state.get("study_plan") if isinstance(state.get("study_plan"), dict) else {}
    plan_tasks = [
        task
        for week in plan.get("weekly", [])
        if isinstance(week, dict)
        for task in week.get("tasks", [])
        if isinstance(task, dict)
    ]
    all_tasks = task_rows + plan_tasks
    completed_tasks = sum(
        str(task.get("status") or "").lower() in {"done", "completed"}
        or bool(task.get("completed"))
        for task in all_tasks
    )

    days_to_exam = None
    try:
        if state.get("exam_date"):
            days_to_exam = max(
                0,
                (date.fromisoformat(str(state["exam_date"])[:10]) - date.today()).days,
            )
    except ValueError:
        pass

    mock_scores = [
        float(item.get("score"))
        for item in state.get("mock_exams", [])
        if isinstance(item, dict) and isinstance(item.get("score"), (int, float))
    ]
    sample_size = len(records)
    return {
        "difficulty_weighted_accuracy": (
            round(weighted_correct / weighted_total * 100, 1)
            if weighted_total
            else None
        ),
        "recent_30d_attempts": len(recent),
        "recent_30d_accuracy": (
            round(recent_later, 1) if recent_later is not None else None
        ),
        "recent_trend_delta": (
            round(recent_later - recent_earlier, 1)
            if recent_later is not None and recent_earlier is not None
            else None
        ),
        "first_attempt_accuracy": (
            round(first_accuracy, 1) if first_accuracy is not None else None
        ),
        "repeat_accuracy": (
            round(repeat_accuracy, 1) if repeat_accuracy is not None else None
        ),
        "repeat_improvement": (
            round(repeat_accuracy - first_accuracy, 1)
            if repeat_accuracy is not None and first_accuracy is not None
            else None
        ),
        "review_recovery_rate": (
            round(len(recovered) / len(repeated_latest) * 100, 1)
            if repeated_latest
            else None
        ),
        "speed_score": round(statistics.median(speeds), 1) if speeds else None,
        "retention_score": (
            round(statistics.mean(retention_values), 1)
            if retention_values
            else None
        ),
        "plan_completion": (
            round(completed_tasks / len(all_tasks) * 100, 1)
            if all_tasks
            else None
        ),
        "days_to_exam": days_to_exam,
        "mock_average": (
            round(statistics.mean(mock_scores), 1) if mock_scores else None
        ),
        "sample_size": sample_size,
        "sample_confidence": round(min(0.97, 1 - math.exp(-sample_size / 35)), 2),
    }
