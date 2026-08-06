from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any


def update_knowledge_state(
    previous: dict[str, Any] | None,
    *,
    is_correct: bool,
    observed_at: str,
    spent_seconds: int | None = None,
    expected_seconds: int = 90,
    difficulty: float = 0.5,
) -> dict[str, Any]:
    """Update a compact BKT + FSRS-inspired knowledge state.

    BKT estimates whether the concept is known; stability/difficulty estimate
    when it should be reviewed. Response time lowers the evidence strength of a
    very slow correct answer and a suspiciously fast wrong guess.
    """

    item = dict(previous or {})
    attempts = int(item.get("attempts", 0)) + 1
    correct_count = int(item.get("correct", 0)) + int(is_correct)
    wrong_count = int(item.get("wrong", 0)) + int(not is_correct)

    prior = float(item.get("mastery_probability", item.get("score", 55.0) / 100))
    prior = max(0.01, min(0.99, prior))
    slip = 0.10 + max(0.0, min(0.12, difficulty * 0.08))
    guess = 0.18 + max(0.0, min(0.12, (1.0 - difficulty) * 0.08))
    learn = 0.12

    if is_correct:
        posterior = prior * (1 - slip) / max(
            prior * (1 - slip) + (1 - prior) * guess,
            1e-9,
        )
    else:
        posterior = prior * slip / max(
            prior * slip + (1 - prior) * (1 - guess),
            1e-9,
        )
    posterior = posterior + (1 - posterior) * learn

    if spent_seconds and expected_seconds > 0:
        time_ratio = spent_seconds / expected_seconds
        if is_correct and time_ratio > 2.0:
            posterior = prior + (posterior - prior) * 0.65
        elif not is_correct and time_ratio < 0.25:
            posterior = min(posterior, prior * 0.8)

    stability = max(0.5, float(item.get("stability_days", 1.0)))
    memory_difficulty = max(1.0, min(10.0, float(item.get("memory_difficulty", 5.0))))
    if is_correct:
        growth = 1.35 + posterior * 1.15
        stability = min(180.0, stability * growth)
        memory_difficulty = max(1.0, memory_difficulty - 0.25)
    else:
        stability = max(0.5, stability * 0.42)
        memory_difficulty = min(10.0, memory_difficulty + 0.65)

    confidence = 1.0 - math.exp(-attempts / 4.0)
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if observed.tzinfo is not None:
            observed = observed.astimezone().replace(tzinfo=None)
    except (TypeError, ValueError):
        observed = datetime.now()
    interval = max(1, round(stability * (0.65 + posterior * 0.7)))
    next_review = observed + timedelta(days=interval)

    item.update(
        {
            "score": round(posterior * 100, 2),
            "mastery_probability": round(posterior, 4),
            "confidence": round(confidence, 4),
            "stability_days": round(stability, 2),
            "memory_difficulty": round(memory_difficulty, 2),
            "attempts": attempts,
            "correct": correct_count,
            "wrong": wrong_count,
            "last_answered_at": observed.isoformat(timespec="seconds"),
            "next_review_at": next_review.isoformat(timespec="seconds"),
            "model_version": "bkt-fsrs-lite-v1",
        }
    )
    return item


def retrievability(item: dict[str, Any], now: datetime | None = None) -> float:
    current = now or datetime.now()
    raw = item.get("last_answered_at") or item.get("last_practiced")
    if not raw:
        return 0.0
    try:
        last = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if last.tzinfo is not None:
            last = last.astimezone().replace(tzinfo=None)
    except (TypeError, ValueError):
        return 0.0
    elapsed = max(0.0, (current - last).total_seconds() / 86400)
    stability = max(0.25, float(item.get("stability_days", 1.0)))
    return round(math.exp(-elapsed / stability), 4)
