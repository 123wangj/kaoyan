from __future__ import annotations

import json
import random
import re
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SUBJECTS = ("数据结构", "计算机组成原理", "操作系统", "计算机网络")
EXAM_DISTRIBUTION = {
    "数据结构": 11,
    "计算机组成原理": 11,
    "操作系统": 10,
    "计算机网络": 8,
}
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _letter(value: object) -> str:
    return "".join(sorted(set(re.findall(r"[A-D]", str(value or "").upper()))))


def _path(data_dir: Path, user_id: str) -> Path:
    safe_user = re.sub(r"[^A-Za-z0-9_.-]", "_", user_id)[:80] or "user"
    return data_dir / "exam_records" / f"{safe_user}.json"


def _read(data_dir: Path, user_id: str) -> list[dict[str, Any]]:
    path = _path(data_dir, user_id)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write(data_dir: Path, user_id: str, records: list[dict[str, Any]]) -> None:
    path = _path(data_dir, user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _public_question(question: dict[str, Any], *, reveal: bool = False) -> dict[str, Any]:
    result = {
        "id": str(question.get("id") or ""),
        "type": question.get("type") or "choice",
        "content": question.get("content") or "",
        "options": question.get("options") or [],
        "subject": question.get("subject") or "",
        "chapter": question.get("chapter") or "",
        "knowledge_points": question.get("knowledge_points") or [],
        "difficulty": question.get("difficulty") or "",
        "source": question.get("source") or "",
        "images": question.get("images") or question.get("image_urls") or [],
    }
    if reveal:
        result.update(
            answer=_letter(question.get("answer")),
            explanation=question.get("explanation") or question.get("analysis") or "暂无解析。",
        )
    return result


def create_exam(
    data_dir: Path,
    user_id: str,
    questions: list[dict[str, Any]],
    count: int = 40,
) -> dict[str, Any]:
    count = max(4, min(int(count), 100))
    pools: dict[str, list[dict[str, Any]]] = {subject: [] for subject in SUBJECTS}
    for question in questions:
        subject = str(question.get("subject") or "")
        if (
            subject in pools
            and question.get("type") == "choice"
            and len(question.get("options") or []) >= 4
            and len(_letter(question.get("answer"))) == 1
        ):
            pools[subject].append(question)
    if any(not pool for pool in pools.values()):
        missing = [subject for subject, pool in pools.items() if not pool]
        raise ValueError("以下科目没有可用选择题：" + "、".join(missing))

    rng = random.SystemRandom()
    if count == 40:
        allocation = dict(EXAM_DISTRIBUTION)
    else:
        base, extra = divmod(count, len(SUBJECTS))
        allocation = {
            subject: base + (1 if index < extra else 0)
            for index, subject in enumerate(SUBJECTS)
        }
    selected: list[dict[str, Any]] = []
    for subject in SUBJECTS:
        take = allocation[subject]
        if len(pools[subject]) < take:
            raise ValueError(f"{subject}可用题目不足 {take} 道")
        selected.extend(rng.sample(pools[subject], take))

    created_at = _now()
    record = {
        "id": uuid.uuid4().hex,
        "title": f"408 统考结构模拟卷 · {created_at[:10]}",
        "status": "in_progress",
        "created_at": created_at,
        "submitted_at": None,
        "duration_seconds": None,
        "questions": [_public_question(q, reveal=True) for q in selected],
        "answers": {},
        "score": None,
        "correct_count": None,
        "report": None,
    }
    with _LOCK:
        records = _read(data_dir, user_id)
        records.append(record)
        _write(data_dir, user_id, records)
    return _serialize(record)


def _serialize(record: dict[str, Any]) -> dict[str, Any]:
    submitted = record.get("status") == "submitted"
    result = {key: value for key, value in record.items() if key != "questions"}
    result["questions"] = [
        _public_question(question, reveal=submitted) for question in record.get("questions", [])
    ]
    return result


def list_exams(data_dir: Path, user_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        records = _read(data_dir, user_id)
    return [
        {
            "id": record.get("id"),
            "title": record.get("title"),
            "status": record.get("status"),
            "created_at": record.get("created_at"),
            "submitted_at": record.get("submitted_at"),
            "question_count": len(record.get("questions") or []),
            "score": record.get("score"),
            "correct_count": record.get("correct_count"),
        }
        for record in reversed(records)
    ]


def recent_exam_insights(
    data_dir: Path,
    user_id: str,
    *,
    days: int = 7,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Aggregate weak-point signals from submitted exams in a recent time window."""
    reference = now or datetime.now(timezone.utc).astimezone()
    cutoff = reference - timedelta(days=max(1, days))
    with _LOCK:
        records = _read(data_dir, user_id)

    recent: list[dict[str, Any]] = []
    for record in records:
        if record.get("status") != "submitted" or not isinstance(record.get("report"), dict):
            continue
        try:
            submitted = datetime.fromisoformat(str(record.get("submitted_at") or ""))
            if submitted.tzinfo is None:
                submitted = submitted.replace(tzinfo=reference.tzinfo)
            if submitted.astimezone(reference.tzinfo) < cutoff:
                continue
        except (TypeError, ValueError):
            continue
        recent.append(record)
    if not recent:
        return None
    recent.sort(key=lambda item: str(item.get("submitted_at") or ""), reverse=True)

    priority_rank = {"high": 3, "medium": 2, "watch": 1}
    aggregated: dict[tuple[str, str], dict[str, Any]] = {}
    for recency, record in enumerate(recent):
        for point in (record.get("report") or {}).get("weak_points") or []:
            name = str(point.get("name") or "").strip()
            subject = str(point.get("subject") or "").strip()
            if not name:
                continue
            key = (subject, name)
            score = (
                priority_rank.get(str(point.get("priority") or "watch"), 1) * 100
                + int(point.get("exam_wrong") or 0) * 20
                + float(point.get("combined_error_rate") or 0)
                - recency * 5
            )
            current = aggregated.get(key)
            if current is None or score > current["rank_score"]:
                aggregated[key] = {
                    **point,
                    "name": name,
                    "subject": subject,
                    "rank_score": score,
                    "source_exam_id": record.get("id"),
                    "source_exam_title": record.get("title"),
                    "source_submitted_at": record.get("submitted_at"),
                }
    weak_points = sorted(aggregated.values(), key=lambda item: item["rank_score"], reverse=True)
    latest = recent[0]
    return {
        "window_days": max(1, days),
        "exam_count": len(recent),
        "latest_exam_id": latest.get("id"),
        "latest_exam_title": latest.get("title"),
        "latest_submitted_at": latest.get("submitted_at"),
        "weak_points": weak_points[:12],
        "diagnosis_overview": (latest.get("report") or {}).get("diagnosis_overview") or {},
        "study_plan": (latest.get("report") or {}).get("study_plan") or {},
    }


def get_exam(data_dir: Path, user_id: str, exam_id: str) -> dict[str, Any] | None:
    with _LOCK:
        record = next((item for item in _read(data_dir, user_id) if item.get("id") == exam_id), None)
    return _serialize(record) if record else None


def _option_text(question: dict[str, Any], letter: str) -> str:
    for option in question.get("options") or []:
        text = str(option)
        if _letter(text) == letter:
            return re.sub(r"^\s*[A-D][.、:：)]?\s*", "", text).strip()
    return ""


def _build_report(
    questions: list[dict[str, Any]],
    answers: dict[str, str],
    learning_state: dict[str, Any],
) -> dict[str, Any]:
    subject_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    kp_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "wrong": 0, "subject": "", "wrong_question_ids": []}
    )
    wrong_details: list[dict[str, Any]] = []
    for question in questions:
        qid = str(question.get("id") or "")
        selected = _letter(answers.get(qid))
        correct = _letter(question.get("answer"))
        subject = str(question.get("subject") or "未分类")
        is_correct = bool(selected and selected == correct)
        subject_stats[subject]["total"] += 1
        subject_stats[subject]["correct"] += int(is_correct)
        points = question.get("knowledge_points") or [question.get("chapter") or "未标注知识点"]
        for point in points:
            point = str(point)
            kp_stats[point]["total"] += 1
            kp_stats[point]["wrong"] += int(not is_correct)
            kp_stats[point]["subject"] = subject
            if not is_correct:
                kp_stats[point]["wrong_question_ids"].append(qid)
        if not is_correct:
            selected_text = _option_text(question, selected) if selected else "未作答"
            focus = str(points[0])
            if not selected:
                reason = "本题未作答，可能是时间分配不足，或对该知识点缺少稳定的解题入口。"
            else:
                reason = (
                    f"你选择了 {selected}（{selected_text or '该干扰项'}）。可能把“{focus}”中的相近概念或适用条件混淆，"
                    "也可能忽略了题干中的限定词；建议对照解析逐项排除。"
                )
            wrong_details.append(
                {
                    "question_id": qid,
                    "subject": subject,
                    "knowledge_points": points,
                    "selected_answer": selected,
                    "correct_answer": correct,
                    "selected_option_text": selected_text,
                    "possible_reason": reason,
                }
            )

    historical: dict[str, dict[str, int]] = defaultdict(lambda: {"attempts": 0, "wrong": 0})
    for item in learning_state.get("answer_records") or []:
        for point in item.get("knowledge_points") or []:
            historical[str(point)]["attempts"] += 1
            historical[str(point)]["wrong"] += int(not item.get("is_correct"))

    weak_points = []
    for point, stats in kp_stats.items():
        history = historical.get(point, {"attempts": 0, "wrong": 0})
        combined_total = stats["total"] + history["attempts"]
        combined_wrong = stats["wrong"] + history["wrong"]
        history_error_rate = (
            round(history["wrong"] / history["attempts"] * 100, 1)
            if history["attempts"] else None
        )
        exam_error_rate = round(stats["wrong"] / stats["total"] * 100, 1) if stats["total"] else 0
        if stats["wrong"] or (history_error_rate is not None and history_error_rate >= 40):
            persistent = bool(stats["wrong"] and history["attempts"] >= 2 and history_error_rate >= 40)
            if stats["wrong"] >= 2 or (persistent and combined_wrong >= 3):
                priority = "high"
                priority_label = "优先补强"
            elif stats["wrong"] or (history_error_rate or 0) >= 40:
                priority = "medium"
                priority_label = "本周巩固"
            else:
                priority = "watch"
                priority_label = "持续观察"

            likely_causes = []
            if persistent:
                likely_causes.append("本卷与历史记录同时失分，说明不是偶发失误，基础概念或判断规则尚未稳定。")
            elif stats["wrong"] and not history["attempts"]:
                likely_causes.append("题库中缺少该知识点的历史样本，本次失分可能来自知识覆盖不足或首次遇到该题型。")
            elif stats["wrong"] and history_error_rate is not None and history_error_rate < 30:
                likely_causes.append("历史表现较好但本卷失分，更像是审题、时间压力或题型迁移造成的波动。")
            if stats["wrong"] >= 2:
                likely_causes.append("同一知识点连续失分，可能只记住了结论，没有形成条件、过程和反例之间的完整知识链。")
            if exam_error_rate >= 50:
                likely_causes.append("本卷错误率达到一半以上，建议优先检查定义边界、适用条件和常见干扰项。")
            if not likely_causes:
                likely_causes.append("当前证据提示存在局部不稳，建议通过少量同类题确认是概念问题还是偶发失误。")

            action_plan = [
                f"概念复盘：用自己的话写出“{point}”的定义、成立条件和一个反例。",
                f"针对训练：完成 5 道基础辨析题和 5 道综合应用题，并记录每个错误选项错在哪里。",
                "验收标准：隔天重做本卷相关错题，再做 3 道新题；连续正确率达到 80% 后再降低优先级。",
            ]
            weak_points.append(
                {
                    "name": point,
                    "subject": stats["subject"],
                    "exam_wrong": stats["wrong"],
                    "exam_total": stats["total"],
                    "history_wrong": history["wrong"],
                    "history_attempts": history["attempts"],
                    "exam_error_rate": exam_error_rate,
                    "history_error_rate": history_error_rate,
                    "combined_error_rate": round(combined_wrong / combined_total * 100, 1) if combined_total else 0,
                    "priority": priority,
                    "priority_label": priority_label,
                    "persistent": persistent,
                    "evidence": (
                        f"本卷 {stats['total']} 题错 {stats['wrong']} 题"
                        + (f"；题库历史 {history['attempts']} 次错 {history['wrong']} 次" if history["attempts"] else "；暂无题库历史样本")
                    ),
                    "likely_causes": likely_causes,
                    "action_plan": action_plan,
                    "wrong_question_ids": stats["wrong_question_ids"],
                }
            )
    priority_rank = {"high": 3, "medium": 2, "watch": 1}
    weak_points.sort(
        key=lambda item: (
            priority_rank[item["priority"]], item["exam_wrong"], item["combined_error_rate"]
        ),
        reverse=True,
    )
    subject_rows = []
    for subject in SUBJECTS:
        stats = subject_stats[subject]
        accuracy = round(stats["correct"] / stats["total"] * 100, 1) if stats["total"] else 0
        subject_rows.append(
            {
                "subject": subject,
                **stats,
                "wrong": stats["total"] - stats["correct"],
                "accuracy": accuracy,
                "level": "优势" if accuracy >= 85 else "基本稳定" if accuracy >= 75 else "需要补强",
            }
        )
    weakest = min(subject_rows, key=lambda item: item["accuracy"])
    unanswered_count = sum(1 for question in questions if not _letter(answers.get(str(question.get("id") or ""))))
    persistent_count = sum(1 for item in weak_points if item["persistent"])
    priority_names = [item["name"] for item in weak_points if item["priority"] == "high"][:3]
    return {
        "summary": f"本次最需要优先补强的是{weakest['subject']}；建议先复盘错题对应知识点，再进行同类题限时训练。",
        "subject_performance": subject_rows,
        "weak_points": weak_points[:12],
        "wrong_details": wrong_details,
        "history_used": bool(learning_state.get("answer_records")),
        "diagnosis_overview": {
            "weakest_subject": weakest["subject"],
            "weakest_subject_accuracy": weakest["accuracy"],
            "unanswered_count": unanswered_count,
            "persistent_weakness_count": persistent_count,
            "high_priority_points": priority_names,
            "evidence_note": (
                "诊断已综合本次试卷与题库历史作答；历史样本越多，长期薄弱判断越可靠。"
                if learning_state.get("answer_records")
                else "当前仅依据本次试卷，建议完成针对训练后用新题复测，避免单次样本误判。"
            ),
        },
        "study_plan": {
            "immediate": [
                f"先复盘{weakest['subject']}全部错题，逐项说明错误选项为何不成立。",
                *([f"优先梳理：{'、'.join(priority_names)}。"] if priority_names else []),
            ],
            "within_week": "按高优先级知识点每天安排 20–30 分钟：概念复述、基础辨析、综合应用各一轮。",
            "verification": "3 天后使用未做过的新题复测；单知识点至少 3 题，正确率达到 80% 且能解释干扰项，才视为阶段性掌握。",
        },
    }


def submit_exam(
    data_dir: Path,
    user_id: str,
    exam_id: str,
    answers: dict[str, Any],
    duration_seconds: int | None,
    learning_state: dict[str, Any],
) -> dict[str, Any] | None:
    with _LOCK:
        records = _read(data_dir, user_id)
        record = next((item for item in records if item.get("id") == exam_id), None)
        if not record:
            return None
        if record.get("status") == "submitted":
            return _serialize(record)
        valid_ids = {str(q.get("id")) for q in record.get("questions") or []}
        normalized = {str(qid): _letter(value) for qid, value in answers.items() if str(qid) in valid_ids}
        correct_count = sum(
            _letter(normalized.get(str(question.get("id")))) == _letter(question.get("answer"))
            for question in record.get("questions") or []
        )
        total = len(record.get("questions") or [])
        record.update(
            status="submitted",
            submitted_at=_now(),
            duration_seconds=max(0, int(duration_seconds or 0)),
            answers=normalized,
            correct_count=correct_count,
            score=round(correct_count / total * 100, 1) if total else 0,
            report=_build_report(record.get("questions") or [], normalized, learning_state),
        )
        _write(data_dir, user_id, records)
    return _serialize(record)
