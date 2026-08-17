from __future__ import annotations

import json
import random
import re
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUBJECTS = ("数据结构", "计算机组成原理", "操作系统", "计算机网络")
QUESTION_COUNT = 40
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _letter(value: object) -> str:
    return "".join(sorted(set(re.findall(r"[A-D]", str(value or "").upper()))))


def _path(data_dir: Path, user_id: str) -> Path:
    safe_user = re.sub(r"[^A-Za-z0-9_.-]", "_", user_id)[:80] or "user"
    return data_dir / "profile_assessments" / f"{safe_user}.json"


def _read(data_dir: Path, user_id: str) -> list[dict[str, Any]]:
    path = _path(data_dir, user_id)
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write(data_dir: Path, user_id: str, records: list[dict[str, Any]]) -> None:
    path = _path(data_dir, user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _difficulty(value: object) -> str:
    text = str(value or "").lower()
    if any(marker in text for marker in ("难", "hard", "提高")):
        return "hard"
    if any(marker in text for marker in ("中", "medium", "一般")):
        return "medium"
    return "easy"


def _public_question(question: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(question.get("id") or ""),
        "type": question.get("type") or "choice",
        "content": question.get("content") or question.get("title") or "",
        "options": question.get("options") or [],
        "subject": question.get("subject") or "",
        "chapter": question.get("chapter") or "",
        "knowledge_points": question.get("knowledge_points") or [],
        "difficulty": question.get("difficulty") or "",
        "images": question.get("images") or ([question.get("image_url")] if question.get("image_url") else []),
    }


def _select_subject_questions(pool: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    rng = random.SystemRandom()
    candidates = list(pool)
    rng.shuffle(candidates)
    selected: list[dict[str, Any]] = []
    used_chapters: set[str] = set()
    used_points: set[str] = set()
    difficulty_counts = defaultdict(int)
    targets = {"easy": 4, "medium": 4, "hard": 2}
    while candidates and len(selected) < count:
        def score(question: dict[str, Any]) -> tuple[int, float]:
            chapter = str(question.get("chapter") or "其他")
            points = {str(value) for value in question.get("knowledge_points") or [] if str(value)}
            level = _difficulty(question.get("difficulty"))
            coverage = (8 if chapter not in used_chapters else 0) + 3 * len(points - used_points)
            balance = 5 if difficulty_counts[level] < targets[level] else 0
            return coverage + balance, rng.random()

        best = max(candidates, key=score)
        candidates.remove(best)
        selected.append(best)
        used_chapters.add(str(best.get("chapter") or "其他"))
        used_points.update(str(value) for value in best.get("knowledge_points") or [] if str(value))
        difficulty_counts[_difficulty(best.get("difficulty"))] += 1
    return selected


def create_assessment(
    data_dir: Path,
    user_id: str,
    questions: list[dict[str, Any]],
    *,
    force: bool = False,
) -> dict[str, Any]:
    with _LOCK:
        records = _read(data_dir, user_id)
        current = next((item for item in reversed(records) if item.get("status") == "in_progress"), None)
        if current and not force:
            return serialize(current)

        pools: dict[str, list[dict[str, Any]]] = {subject: [] for subject in SUBJECTS}
        for question in questions:
            subject = str(question.get("subject") or "")
            if (
                subject in pools
                and question.get("type") in {"choice", "single_choice", "multiple_choice"}
                and len(question.get("options") or []) >= 4
                and _letter(question.get("answer"))
            ):
                pools[subject].append(question)
        per_subject = QUESTION_COUNT // len(SUBJECTS)
        missing = [subject for subject, pool in pools.items() if len(pool) < per_subject]
        if missing:
            raise ValueError("以下科目可用题目不足：" + "、".join(missing))

        selected = []
        for subject in SUBJECTS:
            selected.extend(_select_subject_questions(pools[subject], per_subject))
        random.SystemRandom().shuffle(selected)
        record = {
            "id": uuid.uuid4().hex,
            "status": "in_progress",
            "created_at": _now(),
            "submitted_at": None,
            "duration_seconds": None,
            "questions": [
                {**_public_question(question), "answer": _letter(question.get("answer")),
                 "explanation": question.get("explanation") or question.get("analysis") or ""}
                for question in selected
            ],
            "answers": {},
            "result": None,
        }
        records.append(record)
        _write(data_dir, user_id, records)
        return serialize(record)


def get_assessment(data_dir: Path, user_id: str, assessment_id: str) -> dict[str, Any] | None:
    with _LOCK:
        record = next((item for item in _read(data_dir, user_id) if item.get("id") == assessment_id), None)
    return record


def status(data_dir: Path, user_id: str) -> dict[str, Any]:
    with _LOCK:
        records = _read(data_dir, user_id)
    latest = records[-1] if records else None
    completed = [item for item in records if item.get("status") == "submitted"]
    return {
        "available": True,
        "question_count": QUESTION_COUNT,
        "has_completed": bool(completed),
        "in_progress": bool(latest and latest.get("status") == "in_progress"),
        "assessment": serialize(latest) if latest and latest.get("status") == "in_progress" else None,
        "latest_result": completed[-1].get("result") if completed else None,
        "latest_submitted_at": completed[-1].get("submitted_at") if completed else None,
    }


def grade(record: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    normalized = {str(key): _letter(value) for key, value in answers.items()}
    questions = record.get("questions") or []
    missing = [str(question.get("id")) for question in questions if not normalized.get(str(question.get("id")))]
    if missing:
        raise ValueError(f"还有 {len(missing)} 道题未作答")
    subject_stats = {subject: {"correct": 0, "total": 0, "accuracy": 0.0} for subject in SUBJECTS}
    details = []
    for question in questions:
        qid = str(question.get("id") or "")
        selected = normalized[qid]
        correct_answer = _letter(question.get("answer"))
        correct = selected == correct_answer
        bucket = subject_stats[str(question.get("subject"))]
        bucket["total"] += 1
        bucket["correct"] += int(correct)
        details.append({"question": question, "selected_option": selected, "correct_answer": correct_answer, "is_correct": correct})
    for bucket in subject_stats.values():
        bucket["accuracy"] = round(bucket["correct"] / bucket["total"] * 100, 1) if bucket["total"] else 0.0
    correct_count = sum(int(item["is_correct"]) for item in details)
    return {
        "answers": normalized,
        "details": details,
        "result": {
            "question_count": len(questions),
            "correct_count": correct_count,
            "accuracy": round(correct_count / len(questions) * 100, 1) if questions else 0.0,
            "subjects": subject_stats,
            "weak_subjects": sorted(SUBJECTS, key=lambda subject: subject_stats[subject]["accuracy"]),
        },
    }


def finalize(
    data_dir: Path,
    user_id: str,
    assessment_id: str,
    graded: dict[str, Any],
    duration_seconds: int | None,
) -> dict[str, Any]:
    with _LOCK:
        records = _read(data_dir, user_id)
        record = next((item for item in records if item.get("id") == assessment_id), None)
        if not record:
            raise ValueError("画像测评不存在")
        if record.get("status") == "submitted":
            return serialize(record)
        record.update(
            status="submitted",
            submitted_at=_now(),
            duration_seconds=max(0, int(duration_seconds or 0)),
            answers=graded["answers"],
            result=graded["result"],
        )
        _write(data_dir, user_id, records)
        return serialize(record)


def serialize(record: dict[str, Any]) -> dict[str, Any]:
    submitted = record.get("status") == "submitted"
    return {
        "id": record.get("id"),
        "status": record.get("status"),
        "created_at": record.get("created_at"),
        "submitted_at": record.get("submitted_at"),
        "duration_seconds": record.get("duration_seconds"),
        "question_count": len(record.get("questions") or []),
        "questions": [
            ({**_public_question(question), "answer": question.get("answer"), "explanation": question.get("explanation")}
             if submitted else _public_question(question))
            for question in record.get("questions") or []
        ],
        "answers": record.get("answers") or {},
        "result": record.get("result"),
    }
