from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from kaoyan_ai import db_store
from kaoyan_ai.student_model import retrievability, update_knowledge_state


_LOCK = threading.RLock()
_SUBJECTS = ["数据结构", "计算机组成原理", "操作系统", "计算机网络"]
_UNLABELED_MARKERS = {
    "未标注知识点",
    "未标注",
    "暂无",
    "鏈爣娉ㄧ煡璇嗙偣",
}


def normalize_choice_answer(value: object) -> str:
    """Normalize single or multiple choice answers to sorted unique letters."""
    if isinstance(value, (list, tuple, set)):
        text = "".join(str(item) for item in value)
    else:
        text = str(value or "")
    return "".join(sorted(set(re.findall(r"[A-D]", text.upper()))))


def _is_unlabeled_kp(value: object) -> bool:
    text = str(value or "").strip()
    return not text or any(marker in text for marker in _UNLABELED_MARKERS)


def _canonical_subject(value: object) -> str:
    text = str(value or "").strip()
    aliases = {
        "数据结构": ("数据结构", "鏁版嵁缁撴瀯"),
        "计算机组成原理": ("计算机组成原理", "计算机组成", "计组", "璁＄畻鏈虹粍鎴"),
        "操作系统": ("操作系统", "鎿嶄綔绯荤粺"),
        "计算机网络": ("计算机网络", "计网", "璁＄畻鏈虹綉缁"),
    }
    for canonical, markers in aliases.items():
        if any(marker in text for marker in markers):
            return canonical
    return text or "未知"


def load_learning_state(data_dir: Path, user_id: str) -> dict[str, Any]:
    """优先从 PostgreSQL 加载；PG 失败或用户不存在时回退到 JSON。

    合并策略:PG 提供 answer_records/wrong_questions/mastery 等镜像字段,
    daily_tasks / wrong_book 等以 JSON 文件为权威源(这些只写 JSON,
    避免 PG 空字典覆盖本地已完成的标记)。
    """
    with _LOCK:
        pg_state: dict[str, Any] | None = None
        try:
            pg_state = db_store.load_state(user_id)
        except Exception:
            pg_state = None

        path = _state_path(data_dir, user_id)
        if path.exists():
            json_state = json.loads(path.read_text(encoding="utf-8"))
        else:
            json_state = None

        if pg_state is not None and json_state is not None:
            # PostgreSQL is authoritative for answers, wrong-book entries and
            # mastery. JSON only owns UI task/check-in state and acts as a
            # fallback when a DB collection is genuinely empty.
            json_tasks = json_state.get("daily_tasks") or {}
            if json_tasks:
                pg_state["daily_tasks"] = json_tasks
            for key in ("wrong_book", "mastery"):
                if not pg_state.get(key) and json_state.get(key):
                    pg_state[key] = json_state[key]
            merged_notes = dict(pg_state.get("question_notes") or {})
            for question_id, local_note in (json_state.get("question_notes") or {}).items():
                server_note = merged_notes.get(question_id) or {}
                if str(local_note.get("updated_at") or "") >= str(server_note.get("updated_at") or ""):
                    merged_notes[question_id] = local_note
            pg_state["question_notes"] = merged_notes
            if json_state.get("study_plan"):
                pg_state["study_plan"] = json_state["study_plan"]
            if json_state.get("preferences"):
                pg_state["preferences"] = json_state["preferences"]
            return _normalize_state(pg_state, user_id)

        if pg_state is not None and (pg_state.get("answer_records") or pg_state.get("wrong_questions")):
            return _normalize_state(pg_state, user_id)

        if json_state is not None:
            return _normalize_state(json_state, user_id)

        state = _seed_from_sample_profile(data_dir, user_id)
        _save_state(path, state)
        return state


def _user_exists_in_json(data_dir: Path, user_id: str) -> bool:
    return _state_path(data_dir, user_id).exists()


def save_learning_state(data_dir: Path, user_id: str, state: dict[str, Any]) -> None:
    path = _state_path(data_dir, user_id)
    with _LOCK:
        _save_state(path, _normalize_state(state, user_id))


def answer_records_for_source(
    data_dir: Path,
    user_id: str,
    source: str,
    fallback_records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return records with their full source tag, including the plan task id.

    PostgreSQL's legacy answer_records schema only retains a generic mode. The
    per-user JSON mirror remains the authoritative source for task-scoped tags
    such as ``study_plan:<task_id>``.
    """
    records: list[dict[str, Any]] = []
    path = _state_path(data_dir, user_id)
    with _LOCK:
        try:
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                records = payload.get("answer_records") or []
        except (OSError, ValueError, TypeError):
            records = []
    if not records:
        records = fallback_records or []
    return [record for record in records if record.get("source") == source]


def record_answer(data_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    user_id = payload.get("user_id") or "u1"
    question_id = str(payload.get("question_id") or "").strip()
    subject = _canonical_subject(payload.get("subject"))
    knowledge_points = _knowledge_points(payload)
    selected_option = normalize_choice_answer(payload.get("selected_option"))
    correct_answer = normalize_choice_answer(payload.get("correct_answer"))
    is_correct = bool(payload.get("is_correct"))
    if correct_answer:
        is_correct = selected_option == correct_answer

    now = _now()
    state = load_learning_state(data_dir, user_id)
    record = {
        "question_id": question_id,
        "subject": subject,
        "knowledge_points": knowledge_points,
        "is_correct": is_correct,
        "selected_option": selected_option,
        "correct_answer": correct_answer,
        "source": payload.get("source", "question_bank"),
        "spent_seconds": payload.get("spent_seconds"),
        "difficulty": payload.get("difficulty"),
        "created_at": now,
    }
    state["answer_records"].append(record)

    for point in knowledge_points:
        _update_mastery(
            state,
            point,
            subject,
            is_correct,
            now,
            spent_seconds=payload.get("spent_seconds"),
            difficulty=payload.get("difficulty"),
        )

    if not is_correct:
        wrong = {
            "question_id": question_id,
            "subject": subject,
            "knowledge_points": knowledge_points,
            "error_reason": payload.get("error_reason") or "概念不清",
            "created_at": now,
        }
        state["wrong_questions"].append(wrong)
        _upsert_wrong_book(state, payload, wrong, now)
    elif question_id in state["wrong_book"]:
        item = state["wrong_book"][question_id]
        item["last_correct_at"] = now
        item["correct_after_wrong"] = int(item.get("correct_after_wrong", 0)) + 1
        if item["correct_after_wrong"] >= 2:
            item["status"] = "resolved"
        elif item.get("status") == "open":
            item["status"] = "reviewing"

    adaptation = _adapt_study_plan_after_answer(
        state,
        knowledge_points=knowledge_points,
        is_correct=is_correct,
        now=now,
    )
    save_learning_state(data_dir, user_id, state)
    if adaptation.get("changed") and isinstance(state.get("study_plan"), dict):
        try:
            db_store.upsert_study_plan(user_id, state["study_plan"])
        except Exception:
            pass
    try:
        from kaoyan_ai.memory import SemanticMemory

        for point in knowledge_points:
            model_state = state.get("mastery", {}).get(point, {})
            SemanticMemory(data_dir).remember(
                user_id,
                category="learning_state",
                key=point,
                value={
                    "score": model_state.get("score"),
                    "next_review_at": model_state.get("next_review_at"),
                    "last_result": "correct" if is_correct else "wrong",
                },
                source=f"answer:{question_id}",
                confidence=float(model_state.get("confidence", 0.5)),
            )
    except Exception:
        pass

    # 同步写入 PostgreSQL
    try:
        db_store.insert_answer_record(
            user_id=user_id,
            question_external_id=question_id,
            is_correct=is_correct,
            user_answer=selected_option,
            spent_seconds=payload.get("spent_seconds"),
            error_reason=payload.get("error_reason") if not is_correct else None,
        )
        for point in knowledge_points:
            db_store.update_kp_mastery(user_id, point, subject, is_correct)
        if not is_correct:
            db_store.upsert_wrong_question(
                user_id=user_id,
                question_external_id=question_id,
                error_reason=payload.get("error_reason") or "概念不清",
            )
    except Exception:
        pass  # 写 PG 失败不影响主流程

    return {
        "success": True,
        "is_correct": is_correct,
        "mastery": mastery_summary(state),
        "wrong_book_count": len(wrong_book_items(state, status="open")),
        "student_model": {
            point: state.get("mastery", {}).get(point, {})
            for point in knowledge_points
        },
        "plan_adaptation": adaptation,
    }


def acknowledge_push(data_dir: Path, user_id: str, pushed_ids: list[str]) -> dict[str, Any]:
    state = load_learning_state(data_dir, user_id)
    kp_ids = set(state.get("pushed_knowledge_ids", []))
    q_ids = set(state.get("pushed_question_ids", []))
    for item_id in pushed_ids:
        if item_id.startswith("kp-"):
            kp_ids.add(item_id)
        elif item_id.startswith(("push-q-", "fallback-")):
            q_ids.add(item_id)
    state["pushed_knowledge_ids"] = sorted(kp_ids)
    state["pushed_question_ids"] = sorted(q_ids)
    save_learning_state(data_dir, user_id, state)

    # 同步写入 PG
    try:
        for item_id in pushed_ids:
            if item_id.startswith("kp-"):
                db_store.add_push_history(user_id, "knowledge", item_id)
            elif item_id.startswith(("push-q-", "fallback-")):
                db_store.add_push_history(user_id, "question", item_id)
    except Exception:
        pass

    return {"success": True, "saved_ids": sorted(kp_ids | q_ids)}


def wrong_book_items(state: dict[str, Any], status: str | None = None) -> list[dict[str, Any]]:
    items = list(state.get("wrong_book", {}).values())
    if status and status != "all":
        items = [item for item in items if item.get("status") == status]
    return sorted(
        items,
        key=lambda item: (item.get("status") == "resolved", item.get("last_wrong_at", "")),
        reverse=True,
    )


def yesterday_review_items(
    state: dict[str, Any],
    questions: list[dict[str, Any]],
    *,
    day: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return yesterday's unique attempted questions, wrong answers first."""
    reference = date.fromisoformat(day) if day else date.today()
    target = reference - timedelta(days=1)
    latest: dict[str, dict[str, Any]] = {}
    for record in state.get("answer_records") or []:
        question_id = str(record.get("question_id") or "").strip()
        created_at = str(record.get("created_at") or record.get("timestamp") or "")
        if not question_id or not created_at:
            continue
        try:
            if datetime.fromisoformat(created_at.replace("Z", "+00:00")).date() != target:
                continue
        except ValueError:
            continue
        previous = latest.get(question_id)
        if previous is None or created_at >= str(previous.get("created_at") or ""):
            latest[question_id] = record

    catalog = {str(item.get("id") or ""): item for item in questions}
    rows = []
    for question_id, record in latest.items():
        question = catalog.get(question_id)
        if not question:
            continue
        rows.append(
            {
                "question_id": question_id,
                "was_wrong": not bool(record.get("is_correct")),
                "last_answered_at": record.get("created_at") or record.get("timestamp"),
                "question": question,
            }
        )
    rows.sort(key=lambda item: (not item["was_wrong"], str(item["last_answered_at"])))
    return rows[: max(1, min(int(limit), 20))]


def set_daily_question_goal(data_dir: Path, user_id: str, value: int) -> int:
    goal = max(1, min(int(value), 100))
    state = load_learning_state(data_dir, user_id)
    state.setdefault("preferences", {})["daily_question_goal"] = goal
    save_learning_state(data_dir, user_id, state)
    return goal


def review_wrong_question(
    data_dir: Path,
    user_id: str,
    question_id: str,
    result: str = "reviewed",
) -> dict[str, Any]:
    state = load_learning_state(data_dir, user_id)
    item = state.get("wrong_book", {}).get(question_id)
    if not item:
        return {"success": False, "error": "wrong question not found"}

    now = _now()
    item["review_count"] = int(item.get("review_count", 0)) + 1
    item["last_reviewed_at"] = now
    if result in {"resolved", "mastered"}:
        item["status"] = "resolved"
        for point in item.get("knowledge_points", []):
            _update_mastery(state, point, item.get("subject", "未知"), True, now, delta=8)
    elif result in {"again", "wrong"}:
        item["status"] = "open"
        for point in item.get("knowledge_points", []):
            _update_mastery(state, point, item.get("subject", "未知"), False, now, delta=-8)
    else:
        item["status"] = "reviewing"

    save_learning_state(data_dir, user_id, state)

    # 同步写入 PG
    try:
        if result in {"resolved", "mastered"}:
            db_store.upsert_wrong_question(
                user_id=user_id,
                question_external_id=question_id,
                mastered=True,
            )
    except Exception:
        pass

    return {"success": True, "item": item, "mastery": mastery_summary(state)}


def mastery_summary(state: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for point, data in state.get("mastery", {}).items():
        if _is_unlabeled_kp(point):
            continue
        score = round(float(data.get("score", 50)), 1)
        items.append(
            {
                "knowledge_point": point,
                "subject": _canonical_subject(data.get("subject")),
                "score": score,
                "level": _mastery_level(score),
                "attempts": int(data.get("attempts", 0)),
                "correct": int(data.get("correct", 0)),
                "wrong": int(data.get("wrong", 0)),
                "last_answered_at": data.get("last_answered_at"),
            }
        )
    return sorted(items, key=lambda item: (item["score"], -item["attempts"]))


def memory_review_queue(
    state: dict[str, Any],
    limit: int = 8,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Rank previously studied knowledge points by review urgency.

    The intervals intentionally stay understandable to students: weaker memories
    return sooner, while strong memories gradually stretch to a month.
    """
    current = now or datetime.now()
    queue: list[dict[str, Any]] = []
    for point, item in state.get("mastery", {}).items():
        if _is_unlabeled_kp(point):
            continue
        last_raw = item.get("last_answered_at") or item.get("last_practiced")
        if not last_raw:
            continue
        try:
            last_seen = datetime.fromisoformat(str(last_raw).replace("Z", "+00:00"))
            if last_seen.tzinfo is not None:
                last_seen = last_seen.astimezone().replace(tzinfo=None)
        except (TypeError, ValueError):
            continue

        score = max(0.0, min(100.0, float(item.get("score", 50))))
        recall = retrievability(item, current)
        attempts = max(1, int(item.get("attempts", 1)))
        correct = max(0, int(item.get("correct", 0)))
        accuracy = correct / attempts
        if score < 40:
            interval_days = 1
        elif score < 60:
            interval_days = 3
        elif score < 75:
            interval_days = 7
        elif score < 90:
            interval_days = 14
        else:
            interval_days = 30
        if accuracy < 0.5:
            interval_days = max(1, interval_days // 2)

        next_review = last_seen + timedelta(days=interval_days)
        days_since = max(0, (current - last_seen).days)
        overdue_days = max(0, (current - next_review).days)
        due = current >= next_review
        urgency = (days_since / interval_days) + ((100 - score) / 100) + (1 - recall)
        queue.append(
            {
                "knowledge_point": point,
                "subject": _canonical_subject(item.get("subject")),
                "mastery_score": round(score, 1),
                "last_reviewed_at": last_seen.isoformat(timespec="seconds"),
                "next_review_at": next_review.isoformat(timespec="seconds"),
                "interval_days": interval_days,
                "days_since_review": days_since,
                "overdue_days": overdue_days,
                "is_due": due,
                "urgency": round(urgency, 3),
                "retrievability": recall,
                "confidence": round(float(item.get("confidence", 0.0)), 3),
                "reason": (
                    f"已超过建议复习时间 {overdue_days} 天"
                    if overdue_days
                    else ("今天建议复习" if due else f"{max(1, (next_review - current).days)} 天后复习")
                ),
            }
        )
    queue.sort(
        key=lambda item: (
            not item["is_due"],
            -item["overdue_days"],
            -item["urgency"],
            item["mastery_score"],
        )
    )
    return queue[: max(1, min(int(limit), 50))]


def get_question_note(data_dir: Path, user_id: str, question_id: str) -> dict[str, Any]:
    state = load_learning_state(data_dir, user_id)
    return dict(
        state.get("question_notes", {}).get(
            question_id,
            {
                "question_id": question_id,
                "text": "",
                "drawing": {"version": 1, "strokes": []},
                "updated_at": None,
            },
        )
    )


def save_question_note(
    data_dir: Path,
    user_id: str,
    question_id: str,
    text: str,
    drawing: dict[str, Any],
) -> dict[str, Any]:
    now = _now()
    note = {
        "question_id": question_id,
        "text": text,
        "drawing": drawing,
        "updated_at": now,
    }
    state = load_learning_state(data_dir, user_id)
    state.setdefault("question_notes", {})[question_id] = note
    save_learning_state(data_dir, user_id, state)
    try:
        db_store.upsert_question_note(user_id, question_id, text, drawing)
    except Exception:
        pass
    return note


def delete_question_note(data_dir: Path, user_id: str, question_id: str) -> None:
    state = load_learning_state(data_dir, user_id)
    state.setdefault("question_notes", {}).pop(question_id, None)
    save_learning_state(data_dir, user_id, state)
    try:
        db_store.delete_question_note(user_id, question_id)
    except Exception:
        pass


def question_completion_progress(
    state: dict[str, Any],
    questions: list[dict[str, Any]],
    knowledge_points: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """按“做过的题目数 / 题库题目总数”计算科目、章节和知识点进度。

    进度只表示覆盖率，与正确率、知识点评分以及重复作答次数无关。
    同一道题重复作答只计为完成一题。
    """
    latest_records = _latest_answer_records(state.get("answer_records", []))
    latest_by_id = {
        str(record.get("question_id") or "").strip(): record
        for record in latest_records
        if str(record.get("question_id") or "").strip()
    }
    attempted_ids = set(latest_by_id)
    subject_counts = {
        subject: {"total": 0, "attempted": 0, "correct": 0}
        for subject in _SUBJECTS
    }
    chapter_counts: dict[str, dict[str, Any]] = {}
    point_counts: dict[str, dict[str, Any]] = {}

    kp_by_id: dict[str, dict[str, Any]] = {}
    kp_by_title: dict[tuple[str, str], dict[str, Any]] = {}
    chapter_by_subject: dict[str, list[dict[str, Any]]] = {
        subject: [] for subject in _SUBJECTS
    }
    for point in knowledge_points or []:
        point_id = str(point.get("id") or "").strip()
        title = str(point.get("title") or "").strip()
        subject = _canonical_subject(point.get("subject"))
        if point_id:
            kp_by_id[point_id] = point
        if title:
            kp_by_title[(subject, title)] = point
        chapter_id = str(point.get("chapter_id") or "").strip()
        if chapter_id and not any(
            item.get("chapter_id") == chapter_id
            for item in chapter_by_subject.setdefault(subject, [])
        ):
            chapter_by_subject[subject].append(
                {
                    "chapter_id": chapter_id,
                    "chapter_title": str(point.get("chapter_title") or "").strip(),
                }
            )

    for question in questions or []:
        question_id = str(question.get("id") or "").strip()
        subject = _canonical_subject(question.get("subject"))
        if subject not in subject_counts:
            continue
        attempted = bool(question_id and question_id in attempted_ids)
        answered_correctly = bool(
            attempted and latest_by_id[question_id].get("is_correct")
        )
        subject_counts[subject]["total"] += 1
        if attempted:
            subject_counts[subject]["attempted"] += 1
        if answered_correctly:
            subject_counts[subject]["correct"] += 1

        mapped_points: dict[str, dict[str, Any]] = {}
        for point_id in question.get("knowledge_point_ids") or []:
            point = kp_by_id.get(str(point_id or "").strip())
            if point:
                mapped_points[str(point.get("id") or point.get("title"))] = point
        for title in question.get("knowledge_points") or []:
            point = kp_by_title.get((subject, str(title or "").strip()))
            if point:
                mapped_points[str(point.get("id") or point.get("title"))] = point

        mapped_chapters: dict[str, dict[str, Any]] = {}
        for point in mapped_points.values():
            title = str(point.get("title") or "").strip()
            if title:
                entry = point_counts.setdefault(
                    title,
                    {
                        "subject": subject,
                        "knowledge_point": title,
                        "knowledge_point_id": str(point.get("id") or "").strip(),
                        "chapter_id": str(point.get("chapter_id") or "").strip(),
                        "chapter_title": str(point.get("chapter_title") or "").strip(),
                        "total": 0,
                        "attempted": 0,
                        "correct": 0,
                    },
                )
                entry["total"] += 1
                if attempted:
                    entry["attempted"] += 1
                if answered_correctly:
                    entry["correct"] += 1
            chapter_id = str(point.get("chapter_id") or "").strip()
            if chapter_id:
                mapped_chapters[chapter_id] = point

        # 旧题若缺少知识点 ID，则用题目章名做一次保守匹配。
        if not mapped_chapters:
            raw_chapter = re.sub(
                r"^\s*第?\s*\d+\s*章\s*",
                "",
                str(question.get("chapter") or "").strip(),
            )
            for chapter in chapter_by_subject.get(subject, []):
                chapter_title = str(chapter.get("chapter_title") or "").strip()
                if raw_chapter and (
                    raw_chapter == chapter_title
                    or raw_chapter in chapter_title
                    or chapter_title in raw_chapter
                ):
                    mapped_chapters[str(chapter["chapter_id"])] = chapter
                    break

        for chapter_id, point in mapped_chapters.items():
            key = f"{subject}||{chapter_id}"
            entry = chapter_counts.setdefault(
                key,
                {
                    "subject": subject,
                    "chapter_id": chapter_id,
                    "chapter_title": str(
                        point.get("chapter_title") or point.get("title") or ""
                    ).strip(),
                    "total": 0,
                    "attempted": 0,
                    "correct": 0,
                },
            )
            entry["total"] += 1
            if attempted:
                entry["attempted"] += 1
            if answered_correctly:
                entry["correct"] += 1

    def _finish(entry: dict[str, Any]) -> dict[str, Any]:
        total = int(entry.get("total", 0))
        attempted = min(total, int(entry.get("attempted", 0)))
        correct = min(attempted, int(entry.get("correct", 0)))
        entry["attempted"] = attempted
        entry["correct"] = correct
        entry["wrong"] = attempted - correct
        entry["progress"] = round(attempted / total * 100, 1) if total else 0.0
        entry["accuracy"] = round(correct / attempted * 100, 1) if attempted else 0.0
        return entry

    return {
        "subjects": {
            subject: _finish(values)
            for subject, values in subject_counts.items()
        },
        "chapters": {
            key: _finish(values)
            for key, values in chapter_counts.items()
        },
        "knowledge_points": {
            title: _finish(values)
            for title, values in point_counts.items()
        },
    }


def completion_mastery_summary(
    state: dict[str, Any],
    questions: list[dict[str, Any]],
    knowledge_points: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """把知识点题目覆盖率转换为现有前端使用的掌握度结构。"""
    progress = question_completion_progress(state, questions, knowledge_points)
    items = []
    for title, entry in progress["knowledge_points"].items():
        score = float(entry["progress"])
        items.append(
            {
                "knowledge_point": title,
                "subject": entry["subject"],
                "knowledge_point_id": entry.get("knowledge_point_id", ""),
                "chapter_id": entry.get("chapter_id", ""),
                "chapter_title": entry.get("chapter_title", ""),
                "score": score,
                "level": _mastery_level(score),
                "attempts": entry["attempted"],
                "total_questions": entry["total"],
                "correct": entry["correct"],
                "wrong": entry["wrong"],
                "accuracy": entry["accuracy"],
                "last_answered_at": None,
            }
        )
    return sorted(items, key=lambda item: (item["score"], -item["attempts"], item["knowledge_point"]))


def today_tasks(
    data_dir: Path,
    user_id: str,
    day: str | None = None,
    questions: list[dict[str, Any]] | None = None,
    knowledge_points: list[dict[str, Any]] | None = None,
    exam_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """返回今日任务。

    - task 结构(id / type / knowledge_point / status 等)按日期缓存,确保
      用户重复刷新看到的任务结构一致,完成状态不会丢。
    - 每个 task 的 mastery_score 每次根据当前 state 的 mastery 实时计算,
      不被 cache 锁死,确保「当前掌握度」始终反映最新做题情况。
    """
    state = load_learning_state(data_dir, user_id)
    completion_items = (
        completion_mastery_summary(state, questions, knowledge_points)
        if questions is not None
        else mastery_summary(state)
    )
    task_date = day or date.today().isoformat()
    exam_signature = ""
    if exam_context:
        signature_payload = {
            "latest_exam_id": exam_context.get("latest_exam_id"),
            "latest_submitted_at": exam_context.get("latest_submitted_at"),
            "weak_points": [
                [item.get("subject"), item.get("name"), item.get("priority")]
                for item in (exam_context.get("weak_points") or [])[:6]
            ],
        }
        exam_signature = hashlib.sha1(
            json.dumps(signature_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
    daily_tasks = state.setdefault("daily_tasks", {})
    if task_date not in daily_tasks:
        daily_tasks[task_date] = {
            "date": task_date,
            "tasks": _build_daily_tasks(
                state, task_date, completion_items, exam_context=exam_context
            ),
            "exam_signature": exam_signature,
            "exam_source": exam_context or None,
            "created_at": _now(),
        }
        save_learning_state(data_dir, user_id, state)
    cached = daily_tasks[task_date]
    tasks_changed = _normalize_daily_tasks(cached)
    daily_goal = max(
        1,
        min(int((state.get("preferences") or {}).get("daily_question_goal") or 5), 100),
    )
    for task in cached.get("tasks") or []:
        if task.get("id") != "mixed-practice":
            continue
        if int(task.get("target_count") or 0) != daily_goal:
            task["target_count"] = daily_goal
            task["title"] = (
                f"完成 {daily_goal} 道薄弱点练习"
                if task.get("has_records")
                else f"完成 {daily_goal} 道随机练习"
            )
            task["description"] = re.sub(
                r"\d+\s*道",
                f"{daily_goal} 道",
                str(task.get("description") or ""),
            )
            tasks_changed = True
    if str(cached.get("exam_signature") or "") != exam_signature:
        statuses = {
            str(task.get("id") or ""): (task.get("status"), task.get("completed_at"))
            for task in cached.get("tasks") or []
        }
        refreshed = _build_daily_tasks(
            state, task_date, completion_items, exam_context=exam_context
        )
        for task in refreshed:
            status, completed_at = statuses.get(str(task.get("id") or ""), (None, None))
            if status == "done":
                task["status"] = "done"
                if completed_at:
                    task["completed_at"] = completed_at
        cached["tasks"] = refreshed
        cached["exam_signature"] = exam_signature
        cached["exam_source"] = exam_context or None
        cached["updated_at"] = _now()
        tasks_changed = True
    if not cached.get("tasks"):
        cached["tasks"] = _build_daily_tasks(
            state, task_date, completion_items, exam_context=exam_context
        )
        tasks_changed = True
    if tasks_changed:
        save_learning_state(data_dir, user_id, state)
    # 同步 PG 中的完成状态(以 DB 为准,确保刷新后状态不丢)
    try:
        db_status = db_store.get_daily_task_completions(user_id, task_date)
    except Exception:
        db_status = {}
    for t in cached.get("tasks", []):
        if t.get("id") in db_status and db_status[t["id"]] == "done":
            t["status"] = "done"
    # 实时覆盖 mastery_score 和 description,确保「当前掌握度」反映最新做题情况
    mastery_map = {m["knowledge_point"]: m["score"] for m in completion_items}
    has_records = bool(state.get("answer_records"))
    for t in cached.get("tasks", []):
        is_exam_task = t.get("source") == "recent_exam_report"
        if t.get("type") == "review" and not is_exam_task:
            kp = t.get("knowledge_point")
            score = mastery_map.get(kp)
            if kp and score is not None:
                t["mastery_score"] = score
                t["description"] = (
                    f"当前掌握度约 {int(round(score))}%,"
                    f"先回顾定义、流程和易错点,再完成对应练习。"
                )
            elif not has_records:
                t["mastery_score"] = None
                t["description"] = (
                    f"系统根据考研大纲随机推荐:先阅读「{kp}」知识点,再做 1~2 道配套练习。"
                )
        t["has_records"] = has_records or is_exam_task
    return cached


def complete_daily_task(
    data_dir: Path,
    user_id: str,
    task_id: str,
    day: str | None = None,
) -> dict[str, Any]:
    state = load_learning_state(data_dir, user_id)
    task_date = day or date.today().isoformat()
    if task_date not in state.get("daily_tasks", {}):
        state.setdefault("daily_tasks", {})[task_date] = {
            "date": task_date,
            "tasks": _build_daily_tasks(state, task_date),
            "created_at": _now(),
        }

    task_set = state["daily_tasks"][task_date]
    now = _now()
    found = False
    for task in task_set.get("tasks", []):
        if task.get("id") == task_id:
            task["status"] = "done"
            task["completed_at"] = now
            found = True
            break
    save_learning_state(data_dir, user_id, state)
    # 同步写入 PG (落库持久化)
    try:
        if found:
            db_store.upsert_daily_task_completion(
                user_id=user_id, task_date=task_date, task_id=task_id, status="done"
            )
    except Exception:
        pass
    return {"success": found, "daily_tasks": task_set}


def uncomplete_daily_task(
    data_dir: Path,
    user_id: str,
    task_id: str,
    day: str | None = None,
) -> dict[str, Any]:
    """用户主动撤销一条任务的完成状态(同步清掉 JSON + DB)。"""
    state = load_learning_state(data_dir, user_id)
    task_date = day or date.today().isoformat()
    found = False
    task_set = state.get("daily_tasks", {}).get(task_date)
    if task_set:
        for t in task_set.get("tasks", []):
            if t.get("id") == task_id:
                t["status"] = "todo"
                t.pop("completed_at", None)
                found = True
                break
    if found:
        save_learning_state(data_dir, user_id, state)
    try:
        db_store.delete_daily_task_completion(
            user_id=user_id, task_date=task_date, task_id=task_id
        )
    except Exception:
        pass
    return {"success": True, "task_set": task_set or {}}


def user_profile_payload(
    data_dir: Path,
    user_id: str,
    token_usage: dict[str, int],
    questions: list[dict[str, Any]] | None = None,
    knowledge_points: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # 个人中心也会读取今日任务；这里同步带入试卷上下文，避免随后刷新个人中心时
    # 把刚由试卷报告生成的任务误判为“无试卷来源”并覆盖掉。
    from .exam_store import recent_exam_insights

    state = load_learning_state(data_dir, user_id)
    answer_records = _latest_answer_records(state.get("answer_records", []))
    # 个人中心与题库总览使用同一统计口径：只统计当前题库中仍然存在的题目，
    # 并按 question_id 去重。历史下架题、失效题号和匿名记录不能虚增“已做题数”。
    valid_question_ids: set[str] | None = None
    if questions is not None:
        valid_question_ids = {
            str(question.get("id") or "").strip()
            for question in questions
            if str(question.get("id") or "").strip()
            and _canonical_subject(question.get("subject")) in _SUBJECTS
        }
        answer_records = [
            record
            for record in answer_records
            if str(record.get("question_id") or "").strip() in valid_question_ids
        ]
    progress = question_completion_progress(state, questions or [], knowledge_points)
    if questions is not None:
        # Reuse the exact aggregate behind /user/stats/overview. This prevents
        # the profile and question-bank overview from drifting as data evolves.
        total_count = sum(progress["subjects"][subject]["attempted"] for subject in _SUBJECTS)
        correct_count = sum(progress["subjects"][subject]["correct"] for subject in _SUBJECTS)
        subject_stats = {
            subject: {
                "total": progress["subjects"][subject]["attempted"],
                "correct": progress["subjects"][subject]["correct"],
                "accuracy": progress["subjects"][subject]["accuracy"],
            }
            for subject in _SUBJECTS
        }
    else:
        correct_count = sum(1 for item in answer_records if item.get("is_correct"))
        total_count = len(answer_records)
        subject_stats: dict[str, dict[str, Any]] = {}
        for record in answer_records:
            subject = _canonical_subject(record.get("subject"))
            subject_stats.setdefault(subject, {"total": 0, "correct": 0})
            subject_stats[subject]["total"] += 1
            if record.get("is_correct"):
                subject_stats[subject]["correct"] += 1
        for data in subject_stats.values():
            data["accuracy"] = round(data["correct"] / data["total"] * 100, 1) if data["total"] else 0
    accuracy = round(correct_count / total_count * 100, 1) if total_count else 0.0

    visible_mastery = (
        completion_mastery_summary(state, questions, knowledge_points)
        if questions is not None
        else mastery_summary(state)
    )
    weak_points = [
        {
            "knowledge_point": item["knowledge_point"],
            "subject": item["subject"],
            "knowledge_point_id": item.get("knowledge_point_id", ""),
            "chapter_id": item.get("chapter_id", ""),
            "chapter_title": item.get("chapter_title", ""),
            "score": item["score"],
            "error_count": item["wrong"],
            "attempts": item["attempts"],
            "total_questions": item.get("total_questions", 0),
            "accuracy": item.get("accuracy", 0),
        }
        for item in visible_mastery
        if item["score"] < 75
    ][:8]

    subject_mastery: dict[str, dict[str, Any]] = {}
    for subject in _SUBJECTS:
        values = progress["subjects"][subject]
        subject_mastery[subject] = {
            "score": values["progress"],
            "source": "question_completion",
            "answer_count": values["attempted"],
            "question_count": values["total"],
        }

    if token_usage["total_requests"] == 0:
        token_usage["total_requests"] = max(total_count, 3)
        token_usage["total_tokens"] = token_usage["total_requests"] * 800
    avg_tokens = round(token_usage["total_tokens"] / token_usage["total_requests"])

    open_wrong_items = wrong_book_items(state, status="open")
    if valid_question_ids is not None:
        open_wrong_items = [
            item
            for item in open_wrong_items
            if str(item.get("question_id") or "").strip() in valid_question_ids
        ]

    return {
        "basic_info": {
            "user_id": state.get("user_id", user_id),
            "target_school": state.get("target_school", "未设置"),
            "target_major": state.get("target_major", "未设置"),
            "exam_date": state.get("exam_date", "待定"),
            "chat_summary": state.get("chat_summary", "暂无学习摘要"),
        },
        "answer_stats": {
            "total_questions": total_count,
            "correct_count": correct_count,
            "accuracy": accuracy,
            "wrong_count": len(open_wrong_items),
            "by_subject": subject_stats,
        },
        "subject_mastery": subject_mastery,
        "weak_points": weak_points,
        "mastery": visible_mastery,
        "wrong_book": open_wrong_items,
        "daily_tasks": today_tasks(
            data_dir,
            user_id,
            questions=questions,
            knowledge_points=knowledge_points,
            exam_context=recent_exam_insights(data_dir, user_id, days=7),
        ),
        "token_usage": {
            "total_tokens": token_usage["total_tokens"],
            "total_requests": token_usage["total_requests"],
            "avg_tokens_per_request": avg_tokens,
        },
    }


def _build_daily_tasks(
    state: dict[str, Any],
    task_date: str,
    mastery_items: list[dict[str, Any]] | None = None,
    exam_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """基于用户真实掌握度 / 错题数据,动态生成今日任务。

    - 有做题记录:用 mastery 真实分数 + 错题;
    - 没做题记录:从考研科目随机抽 3 个高频知识点 + 0 错题,并把 mastery_score
      标为 None,前端显示"暂无做题记录"而不是写死的 50%。
    """
    has_records = bool(state.get("answer_records"))
    daily_goal = max(
        1,
        min(int((state.get("preferences") or {}).get("daily_question_goal") or 5), 100),
    )

    # 1) 选 3 个薄弱知识点(真实数据)或 fallback(无做题记录)
    mastery_points = mastery_items if mastery_items is not None else mastery_summary(state)
    exam_points: list[dict[str, Any]] = []
    for item in (exam_context or {}).get("weak_points") or []:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        exam_points.append(
            {
                "knowledge_point": name,
                "subject": item.get("subject") or "未知",
                "score": max(0, 100 - float(item.get("combined_error_rate") or 0)),
                "exam_report": item,
            }
        )
    weak_points: list[dict[str, Any]] = []
    seen_points: set[str] = set()
    for point in [*exam_points, *mastery_points]:
        name = str(point.get("knowledge_point") or "").strip()
        if not name or name in seen_points:
            continue
        seen_points.add(name)
        weak_points.append(point)
        if len(weak_points) >= 3:
            break
    has_learning_data = has_records or bool(weak_points) or bool(exam_context)
    fallback_points = [
        {"knowledge_point": "线性表", "subject": "数据结构", "score": 50},
        {"knowledge_point": "指令系统", "subject": "计算机组成原理", "score": 50},
        {"knowledge_point": "页表", "subject": "操作系统", "score": 50},
        {"knowledge_point": "TCP 三次握手", "subject": "计算机网络", "score": 50},
    ]
    import random
    rng = random.Random(f"{state.get('user_id','u1')}|{task_date}")
    if not weak_points:
        weak_points = list(rng.sample(fallback_points, k=3))

    tasks: list[dict[str, Any]] = []

    # 任务 1..3:复习具体知识点。今日任务闭环不放泛化的入口任务。
    for idx, point in enumerate(weak_points[:3], 1):
        score = point.get("score")
        score_text = f"{int(round(score))}%" if score is not None else "暂无做题记录"
        report_point = point.get("exam_report") or {}
        if report_point:
            cause = (report_point.get("likely_causes") or [""])[0]
            action = (report_point.get("action_plan") or [""])[0]
            desc = "；".join(
                value for value in [
                    f"最近试卷诊断：{report_point.get('evidence') or '该知识点存在失分'}",
                    cause,
                    action,
                ] if value
            )
        elif has_learning_data:
            desc = f"当前掌握度约 {score_text}，先回顾定义、流程和易错点，再完成对应练习。"
        else:
            desc = f"系统根据考研大纲随机推荐:先阅读「{point['knowledge_point']}」知识点,再做 1~2 道配套练习。"
        tasks.append(
            {
                "id": "review-kp-" + _stable_task_suffix(point["knowledge_point"]),
                "type": "review",
                "title": (
                    f"试卷薄弱点复盘：{point['knowledge_point']}"
                    if report_point else f"复习知识点:{point['knowledge_point']}"
                ),
                "description": desc,
                "subject": point.get("subject", "未知"),
                "knowledge_point": point["knowledge_point"],
                "mastery_score": score,
                "target_count": 1,
                "status": "todo",
                "has_records": has_learning_data,
                "source": "recent_exam_report" if report_point else "learning_profile",
                "source_exam_id": report_point.get("source_exam_id"),
                "report_priority": report_point.get("priority"),
                "report_priority_label": report_point.get("priority_label"),
                "report_evidence": report_point.get("evidence"),
                "related_exam_question_ids": report_point.get("wrong_question_ids") or [],
            }
        )

    # 任务 4..N:复盘错题(仅当有错题时)
    wrongs = wrong_book_items(state, status="open")[:3]
    for idx, item in enumerate(wrongs, 1):
        question_text = str(item.get("content") or item.get("title") or "").strip()
        task_title = (
            f"复盘错题：{question_text}"
            if question_text
            else "复盘一道待解决错题"
        )
        tasks.append(
            {
                "id": "wrong-review-" + _stable_task_suffix(item.get("question_id")),
                "type": "wrong_review",
                "title": task_title,
                "description": "重新做一遍,写出当时错因和正确突破口。",
                "subject": item.get("subject", "未知"),
                "knowledge_point": "、".join(item.get("knowledge_points", [])),
                "question_id": item.get("question_id"),
                "target_count": 1,
                "status": "todo",
                "has_records": has_learning_data,
            }
        )

    # 任务最后:薄弱点混合练习(有 records 时)或随机题(无 records)
    if exam_points:
        mixed_desc = (
            "根据最近一周试卷报告，围绕"
            + "、".join(point["knowledge_point"] for point in exam_points[:3])
            + f"进行 {daily_goal} 道新题复测，优先验证高优先级薄弱点。"
        )
    elif has_learning_data:
        mixed_desc = "优先选择掌握度低于 75% 的知识点。"
    else:
        mixed_desc = f"系统随机抽 {daily_goal} 道中等题,先摸底掌握度。"
    tasks.append(
        {
            "id": "mixed-practice",
            "type": "practice",
            "title": f"完成 {daily_goal} 道薄弱点练习" if has_learning_data else f"完成 {daily_goal} 道随机练习",
            "description": mixed_desc,
            "target_count": daily_goal,
            "status": "todo",
            "has_records": has_learning_data,
            "source": "recent_exam_report" if exam_points else "learning_profile",
            "source_exam_id": (exam_context or {}).get("latest_exam_id"),
            "knowledge_points": [point["knowledge_point"] for point in exam_points[:3]],
        }
    )
    return tasks


def _normalize_daily_tasks(task_set: dict[str, Any]) -> bool:
    """清理历史缓存中的泛化任务,保证第一项始终是具体任务。"""

    tasks = task_set.get("tasks")
    if not isinstance(tasks, list):
        task_set["tasks"] = []
        return True

    generic_ids = {"daily-push"}
    generic_titles = {"完成今日推送练习"}
    concrete_tasks = [
        task for task in tasks
        if task.get("id") not in generic_ids
        and task.get("type") != "daily_push"
        and task.get("title") not in generic_titles
        and not (
            task.get("type") in {"review", "wrong_review"}
            and _is_unlabeled_kp(task.get("knowledge_point"))
        )
    ]
    if len(concrete_tasks) != len(tasks):
        task_set["tasks"] = concrete_tasks
        return True
    return False


def _stable_task_suffix(value: object) -> str:
    import hashlib

    return hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()[:10]


def _latest_answer_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use the latest attempt per question for progress and accuracy."""
    latest: dict[str, dict[str, Any]] = {}
    anonymous: list[dict[str, Any]] = []
    for record in records:
        question_id = str(record.get("question_id") or "").strip()
        if question_id:
            latest[question_id] = record
        else:
            anonymous.append(record)
    return list(latest.values()) + anonymous


def _update_mastery(
    state: dict[str, Any],
    point: str,
    subject: str,
    is_correct: bool,
    now: str,
    delta: int | None = None,
    spent_seconds: int | None = None,
    difficulty: float | str | None = None,
) -> None:
    mastery = state.setdefault("mastery", {})
    item = mastery.setdefault(
        point,
        {
            "subject": subject,
            "score": 55.0,
            "attempts": 0,
            "correct": 0,
            "wrong": 0,
        },
    )
    item["subject"] = subject or item.get("subject", "未知")
    if delta is None:
        legacy_score = float(item.get("score", 55.0))
        difficulty_value = {
            "基础": 0.3,
            "中等": 0.5,
            "较难": 0.75,
        }.get(str(difficulty), 0.5)
        updated = update_knowledge_state(
            item,
            is_correct=is_correct,
            observed_at=now,
            spent_seconds=int(spent_seconds) if spent_seconds else None,
            difficulty=difficulty_value,
        )
        item.clear()
        item.update(updated)
        # Keep the public 0..100 score backward compatible while exposing the
        # probabilistic estimate separately as mastery_probability.
        item["score"] = max(
            0.0,
            min(100.0, legacy_score + (10 if is_correct else -18)),
        )
    else:
        item["attempts"] = int(item.get("attempts", 0)) + 1
        if is_correct:
            item["correct"] = int(item.get("correct", 0)) + 1
        else:
            item["wrong"] = int(item.get("wrong", 0)) + 1
        item["score"] = max(0.0, min(100.0, float(item.get("score", 55.0)) + delta))
        item["mastery_probability"] = round(float(item["score"]) / 100, 4)
        item["last_answered_at"] = now
    item["level"] = _mastery_level(float(item["score"]))


def _adapt_study_plan_after_answer(
    state: dict[str, Any],
    *,
    knowledge_points: list[str],
    is_correct: bool,
    now: str,
) -> dict[str, Any]:
    """Adjust future executable tasks using the latest learning evidence."""

    plan = state.get("study_plan")
    if not isinstance(plan, dict):
        return {"changed": False, "reason": "no_active_plan"}
    touched: list[str] = []
    point_set = set(knowledge_points)
    for week in plan.get("weekly", []):
        for task in week.get("tasks", []):
            if task.get("status") == "completed":
                continue
            if not point_set.intersection(task.get("knowledge_points") or []):
                continue
            task["adaptation_priority"] = "high" if not is_correct else "normal"
            current_minutes = int(task.get("estimated_minutes") or 60)
            if not is_correct:
                task["estimated_minutes"] = min(240, current_minutes + 15)
                task["adaptation_reason"] = "最新同知识点作答错误，增加复习与纠错时间"
            else:
                task["adaptation_reason"] = "最新同知识点作答正确，保持原计划并继续验证"
            touched.append(str(task.get("id") or ""))
    if touched:
        plan.setdefault("adaptation_log", []).append(
            {
                "at": now,
                "knowledge_points": knowledge_points,
                "is_correct": is_correct,
                "task_ids": touched,
            }
        )
        plan["updated_at"] = now
    return {
        "changed": bool(touched),
        "task_ids": touched,
        "reason": "answer_feedback",
    }


def _upsert_wrong_book(
    state: dict[str, Any],
    payload: dict[str, Any],
    wrong: dict[str, Any],
    now: str,
) -> None:
    wrong_book = state.setdefault("wrong_book", {})
    question_id = wrong["question_id"]
    item = wrong_book.setdefault(
        question_id,
        {
            "question_id": question_id,
            "wrong_count": 0,
            "review_count": 0,
            "correct_after_wrong": 0,
            "status": "open",
            "created_at": now,
        },
    )
    item.update(
        {
            "subject": wrong["subject"],
            "knowledge_points": wrong["knowledge_points"],
            "error_reason": wrong["error_reason"],
            "content": payload.get("question_content") or payload.get("content") or item.get("content", ""),
            "options": payload.get("options") or item.get("options", []),
            "selected_option": payload.get("selected_option", ""),
            "correct_answer": payload.get("correct_answer", ""),
            "explanation": payload.get("explanation", ""),
            "source": payload.get("source", "question_bank"),
            "status": "open",
            "last_wrong_at": now,
        }
    )
    item["wrong_count"] = int(item.get("wrong_count", 0)) + 1


def _knowledge_points(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("knowledge_points")
    if isinstance(raw, list):
        points = [str(item).strip() for item in raw if str(item).strip()]
    else:
        point = str(payload.get("knowledge_point") or "").strip()
        points = [point] if point else []
    return list(dict.fromkeys(point for point in points if not _is_unlabeled_kp(point)))


def _seed_from_sample_profile(data_dir: Path, user_id: str) -> dict[str, Any]:
    """Create a genuinely empty learning state for a new user.

    The sample profile is fixture/demo data and must never become a real user's
    answer history. Keeping this helper name avoids changing existing callers.
    """
    return _normalize_state({"user_id": user_id}, user_id)


def _normalize_state(state: dict[str, Any], user_id: str) -> dict[str, Any]:
    state.setdefault("version", 1)
    state["user_id"] = state.get("user_id") or user_id
    state.setdefault("answer_records", [])
    state.setdefault("wrong_questions", [])
    state.setdefault("wrong_book", {})
    state.setdefault("mastery", {})
    state.setdefault("daily_tasks", {})
    state.setdefault("pushed_knowledge_ids", [])
    state.setdefault("pushed_question_ids", [])
    state.setdefault("question_notes", {})
    state.setdefault("study_plan", None)  # 学习计划(若已制定)
    state.setdefault("preferences", {})
    state["mastery"] = {
        point: data
        for point, data in state.get("mastery", {}).items()
        if not _is_unlabeled_kp(point)
    }
    for collection_name in ("answer_records", "wrong_questions"):
        for item in state.get(collection_name, []):
            item["subject"] = _canonical_subject(item.get("subject"))
            raw_points = item.get("knowledge_points") or []
            if not isinstance(raw_points, list):
                raw_points = [raw_points]
            item["knowledge_points"] = [
                point for point in raw_points
                if not _is_unlabeled_kp(point)
            ]
    for item in state.get("wrong_book", {}).values():
        item["subject"] = _canonical_subject(item.get("subject"))
        raw_points = item.get("knowledge_points") or []
        if not isinstance(raw_points, list):
            raw_points = [raw_points]
        item["knowledge_points"] = [
            point for point in raw_points
            if not _is_unlabeled_kp(point)
        ]
    return state


def _state_path(data_dir: Path, user_id: str) -> Path:
    safe_user_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", user_id or "anonymous")
    return data_dir / "users" / f"{safe_user_id}.json"


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Each Gunicorn worker needs its own temporary path. A shared
    # ``user.json.tmp`` lets one worker replace the file while another still
    # expects it to exist, which can surface as a transient 500 on first load.
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
            tmp_path = Path(handle.name)
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _mastery_level(score: float) -> str:
    if score >= 85:
        return "mastered"
    if score >= 70:
        return "stable"
    if score >= 50:
        return "weak"
    return "danger"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
