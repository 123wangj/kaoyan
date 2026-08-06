"""PostgreSQL ↔ 学习状态 dict 的双向转换。

将原 learning.py 里的 state 字典结构（answer_records / wrong_questions /
wrong_book / mastery / daily_tasks / pushed_*）映射到 PostgreSQL 表。

约定：state 是「合并视图」，写入时拆解为各表操作，读取时重新组装。
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from kaoyan_ai import db


# ============================================================
# 读：把 PG 表组装成 state dict（保持与原 JSON 版兼容）
# ============================================================
def _user_id_to_pk(user_id: str) -> int | None:
    row = db.fetch_one("SELECT id FROM users WHERE user_id = %s", (user_id,))
    return int(row["id"]) if row else None


def _row_to_answer_record(row: dict) -> dict[str, Any]:
    return {
        "question_id": row.get("external_id") or "",
        "subject": row.get("subject_name") or "未知",
        "knowledge_points": row.get("knowledge_points") or ["未标注知识点"],
        "is_correct": bool(row.get("is_correct")),
        "selected_option": row.get("user_answer") or "",
        "correct_answer": row.get("answer") or "",
        "source": "question_bank",
        "created_at": _iso(row.get("created_at")),
    }


def _row_to_wrong_question(row: dict) -> dict[str, Any]:
    return {
        "question_id": row.get("external_id") or "",
        "subject": row.get("subject_name") or "未知",
        "knowledge_points": row.get("knowledge_points") or ["未标注知识点"],
        "error_reason": row.get("notes") or "概念不清",
        "created_at": _iso(row.get("last_error_at")),
    }


def _row_to_wrong_book_item(row: dict) -> dict[str, Any]:
    return {
        "question_id": row.get("external_id") or "",
        "subject": row.get("subject_name") or "未知",
        "knowledge_points": row.get("knowledge_points") or [],
        "error_reason": row.get("notes") or "",
        "wrong_count": int(row.get("error_count") or 0),
        "review_count": 0,
        "correct_after_wrong": 0,
        "status": "resolved" if row.get("mastered") else "open",
        "mastered": bool(row.get("mastered")),
        "mastered_at": _iso(row.get("mastered_at")),
        "last_wrong_at": _iso(row.get("last_error_at")),
        "content": row.get("stem") or "",
        "options": row.get("options") or [],
        "selected_option": "",
        "correct_answer": row.get("answer") or "",
        "explanation": row.get("analysis") or "",
    }


def _iso(ts) -> str:
    if ts is None:
        return datetime.now().isoformat(timespec="seconds")
    if isinstance(ts, str):
        return ts
    if isinstance(ts, datetime):
        return ts.isoformat(timespec="seconds")
    if isinstance(ts, date):
        return ts.isoformat()
    return str(ts)


def load_state(user_id: str) -> dict[str, Any]:
    """从 PG 组装 state dict；若 PG 无该用户则返回空 state。"""
    state: dict[str, Any] = {
        "version": 1,
        "user_id": user_id,
        "answer_records": [],
        "wrong_questions": [],
        "wrong_book": {},
        "mastery": {},
        "daily_tasks": {},
        "pushed_knowledge_ids": [],
        "pushed_question_ids": [],
        "question_notes": {},
    }

    user_pk = _user_id_to_pk(user_id)
    if user_pk is None:
        return state

    # 用户基础信息
    u = db.fetch_one(
        "SELECT target_school, target_major, exam_date FROM users WHERE id = %s",
        (user_pk,),
    )
    if u:
        state["target_school"] = u.get("target_school")
        state["target_major"] = u.get("target_major")
        state["exam_date"] = u.get("exam_date").isoformat() if u.get("exam_date") else None

    # 做题记录
    ar_rows = db.fetch_all(
        """
        SELECT ar.*, q.external_id, q.answer, q.analysis,
               s.name AS subject_name,
               ARRAY(
                   SELECT kp.name
                   FROM question_kp qkp
                   JOIN knowledge_points kp ON qkp.knowledge_point_id = kp.id
                   WHERE qkp.question_id = q.id
                   ORDER BY kp.name
               ) AS knowledge_points
        FROM answer_records ar
        LEFT JOIN questions q ON ar.question_id = q.id
        LEFT JOIN subjects  s ON q.subject_id  = s.id
        WHERE ar.user_id = %s
        ORDER BY ar.created_at
        """,
        (user_pk,),
    )
    state["answer_records"] = [_row_to_answer_record(r) for r in ar_rows]

    # 错题本
    wq_rows = db.fetch_all(
        """
        SELECT wq.*, q.external_id, q.stem, q.options, q.answer, q.analysis,
               s.name AS subject_name,
               ARRAY(
                   SELECT kp.name
                   FROM question_kp qkp
                   JOIN knowledge_points kp ON qkp.knowledge_point_id = kp.id
                   WHERE qkp.question_id = q.id
                   ORDER BY kp.name
               ) AS knowledge_points
        FROM wrong_questions wq
        LEFT JOIN questions q ON wq.question_id = q.id
        LEFT JOIN subjects  s ON q.subject_id  = s.id
        WHERE wq.user_id = %s
        ORDER BY wq.last_error_at
        """,
        (user_pk,),
    )
    state["wrong_questions"] = [_row_to_wrong_question(r) for r in wq_rows]
    state["wrong_book"] = {r["external_id"]: _row_to_wrong_book_item(r) for r in wq_rows if r.get("external_id")}

    # 知识点掌握度
    kp_rows = db.fetch_all(
        """
        SELECT kp.id AS kp_id, kp.name AS kp_name, s.name AS subject_name,
               km.attempt_count, km.correct_count, km.mastery_score, km.last_practiced
        FROM kp_mastery km
        JOIN knowledge_points kp ON km.knowledge_point_id = kp.id
        LEFT JOIN subjects s ON kp.subject_id = s.id
        WHERE km.user_id = %s
        """,
        (user_pk,),
    )
    for r in kp_rows:
        score = round(max(0.0, min(1.0, float(r.get("mastery_score") or 0))) * 100, 1)
        kp_name = r.get("kp_name") or f"kp#{r.get('kp_id')}"
        state["mastery"][kp_name] = {
            "subject": r.get("subject_name") or "未知",
            "score": score,
            "attempts": int(r.get("attempt_count") or 0),
            "correct": int(r.get("correct_count") or 0),
            "wrong": max(0, int(r.get("attempt_count") or 0) - int(r.get("correct_count") or 0)),
            "last_answered_at": _iso(r.get("last_practiced")),
        }

    # 推送历史
    ph_rows = db.fetch_all(
        "SELECT item_type, item_id FROM push_history WHERE user_id = %s",
        (user_pk,),
    )
    for r in ph_rows:
        if r["item_type"] == "knowledge":
            state["pushed_knowledge_ids"].append(r["item_id"])
        elif r["item_type"] == "question":
            state["pushed_question_ids"].append(r["item_id"])

    try:
        _ensure_question_notes_table()
        note_rows = db.fetch_all(
            """
            SELECT question_external_id, text_content, drawing, updated_at
            FROM question_notes
            WHERE user_id = %s
            """,
            (user_pk,),
        )
        for row in note_rows:
            drawing = row.get("drawing") or {"version": 1, "strokes": []}
            if isinstance(drawing, str):
                drawing = json.loads(drawing)
            question_id = str(row.get("question_external_id") or "")
            state["question_notes"][question_id] = {
                "question_id": question_id,
                "text": row.get("text_content") or "",
                "drawing": drawing,
                "updated_at": _iso(row.get("updated_at")),
            }
    except Exception:
        pass

    return state


# ============================================================
# 写：把单条 answer / wrong / push 写入 PG
# ============================================================
def _ensure_user_pk(user_id: str) -> int:
    """如果用户不存在则创建（取 sample_user_profile.json 的默认值）。"""
    pk = _user_id_to_pk(user_id)
    if pk is not None:
        return pk
    db.execute(
        """
        INSERT INTO users (user_id, nickname) VALUES (%s, %s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id, user_id),
    )
    pk = _user_id_to_pk(user_id)
    if pk is None:
        raise RuntimeError(f"无法创建/查找用户 {user_id}")
    return pk


def _find_question_id_by_external(external_id: str) -> int | None:
    if not external_id:
        return None
    row = db.fetch_one("SELECT id FROM questions WHERE external_id = %s", (external_id,))
    return int(row["id"]) if row else None


def _upsert_kp_mastery(user_pk: int, kp_name: str, subject_name: str, is_correct: bool) -> None:
    """更新知识点掌握度（0~1 浮点制）。"""
    if not kp_name or kp_name == "未标注知识点":
        return
    # 找或建 kp
    kp_row = db.fetch_one(
        """
        SELECT kp.id
        FROM knowledge_points kp
        LEFT JOIN subjects s ON s.id = kp.subject_id
        WHERE kp.name = %s
          AND (%s = '' OR s.name = %s)
        ORDER BY kp.id
        LIMIT 1
        """,
        (kp_name, subject_name or "", subject_name or ""),
    )
    if kp_row is None:
        sub_id_row = db.fetch_one("SELECT id FROM subjects WHERE name = %s", (subject_name,))
        sub_id = int(sub_id_row["id"]) if sub_id_row else None
        db.execute(
            "INSERT INTO knowledge_points (subject_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (sub_id, kp_name),
        )
        kp_row = db.fetch_one(
            """
            SELECT kp.id
            FROM knowledge_points kp
            LEFT JOIN subjects s ON s.id = kp.subject_id
            WHERE kp.name = %s
              AND (%s = '' OR s.name = %s)
            ORDER BY kp.id
            LIMIT 1
            """,
            (kp_name, subject_name or "", subject_name or ""),
        )
    if kp_row is None:
        return
    kp_id = int(kp_row["id"])

    # 累加计数
    # PostgreSQL stores mastery on a 0..1 scale. Keep it equivalent to the
    # JSON algorithm: baseline 55%, correct +10%, wrong -18%.
    mastery_delta = 0.10 if is_correct else -0.18
    initial_score = 0.65 if is_correct else 0.37
    correct_inc = 1 if is_correct else 0
    db.execute(
        """
        INSERT INTO kp_mastery (user_id, knowledge_point_id, attempt_count, correct_count, mastery_score, last_practiced)
        VALUES (%s, %s, 1, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id, knowledge_point_id) DO UPDATE SET
            attempt_count  = kp_mastery.attempt_count + 1,
            correct_count  = kp_mastery.correct_count + EXCLUDED.correct_count,
            mastery_score  = LEAST(1.0, GREATEST(0.0, kp_mastery.mastery_score + %s)),
            last_practiced = CURRENT_TIMESTAMP
        """,
        (user_pk, kp_id, correct_inc, initial_score, mastery_delta),
    )


def insert_answer_record(
    user_id: str,
    question_external_id: str,
    is_correct: bool,
    user_answer: str | None = None,
    spent_seconds: int | None = None,
    error_reason: str | None = None,
    mode: str = "practice",
) -> None:
    user_pk = _ensure_user_pk(user_id)
    qid = _find_question_id_by_external(question_external_id)
    db.execute(
        """
        INSERT INTO answer_records
            (user_id, question_id, is_correct, user_answer, spent_seconds, error_reason, mode)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (user_pk, qid, is_correct, user_answer, spent_seconds, error_reason, mode),
    )


def upsert_wrong_question(
    user_id: str,
    question_external_id: str,
    error_reason: str | None = None,
    mastered: bool = False,
) -> None:
    user_pk = _ensure_user_pk(user_id)
    qid = _find_question_id_by_external(question_external_id)
    if qid is None:
        return
    db.execute(
        """
        INSERT INTO wrong_questions
            (user_id, question_id, error_count, last_error_at, mastered, notes)
        VALUES (%s, %s, 1, CURRENT_TIMESTAMP, %s, %s)
        ON CONFLICT (user_id, question_id) DO UPDATE SET
            error_count   = wrong_questions.error_count + 1,
            last_error_at = CURRENT_TIMESTAMP,
            mastered      = EXCLUDED.mastered,
            notes         = COALESCE(EXCLUDED.notes, wrong_questions.notes)
        """,
        (user_pk, qid, mastered, error_reason),
    )


def add_push_history(user_id: str, item_type: str, item_id: str) -> None:
    user_pk = _ensure_user_pk(user_id)
    db.execute(
        """
        INSERT INTO push_history (user_id, item_type, item_id)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, item_type, item_id) DO NOTHING
        """,
        (user_pk, item_type, item_id),
    )


def update_kp_mastery(user_id: str, kp_name: str, subject_name: str, is_correct: bool) -> None:
    user_pk = _ensure_user_pk(user_id)
    _upsert_kp_mastery(user_pk, kp_name, subject_name, is_correct)


def _ensure_question_notes_table() -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS question_notes (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            question_external_id VARCHAR(128) NOT NULL,
            text_content TEXT NOT NULL DEFAULT '',
            drawing JSONB NOT NULL DEFAULT '{"version":1,"strokes":[]}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, question_external_id)
        )
        """
    )


def upsert_question_note(
    user_id: str,
    question_external_id: str,
    text_content: str,
    drawing: dict[str, Any],
) -> None:
    _ensure_question_notes_table()
    user_pk = _ensure_user_pk(user_id)
    db.execute(
        """
        INSERT INTO question_notes
            (user_id, question_external_id, text_content, drawing, updated_at)
        VALUES (%s, %s, %s, %s::jsonb, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id, question_external_id) DO UPDATE SET
            text_content = EXCLUDED.text_content,
            drawing = EXCLUDED.drawing,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            user_pk,
            question_external_id,
            text_content,
            json.dumps(drawing, ensure_ascii=False),
        ),
    )


def delete_question_note(user_id: str, question_external_id: str) -> None:
    _ensure_question_notes_table()
    user_pk = _ensure_user_pk(user_id)
    db.execute(
        "DELETE FROM question_notes WHERE user_id = %s AND question_external_id = %s",
        (user_pk, question_external_id),
    )


# ============================================================
# 学习计划 / 每日任务完成 (DB 持久化)
# ============================================================
def upsert_study_plan(user_id: str, plan: dict) -> None:
    """保存/更新用户学习计划(整段 JSON 入库)。"""
    user_pk = _ensure_user_pk(user_id)
    db.execute(
        """
        INSERT INTO study_plans (user_id, plan, updated_at)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE SET
            plan = EXCLUDED.plan,
            updated_at = CURRENT_TIMESTAMP
        """,
        (user_pk, json.dumps(plan, ensure_ascii=False)),
    )


def get_study_plan(user_id: str) -> dict | None:
    user_pk = _ensure_user_pk(user_id)
    row = db.fetch_one("SELECT plan, updated_at FROM study_plans WHERE user_id = %s", (user_pk,))
    if not row:
        return None
    plan = row.get("plan")
    if isinstance(plan, str):
        try:
            return json.loads(plan)
        except Exception:
            return None
    return plan


def upsert_daily_task_completion(user_id: str, task_date: str, task_id: str, status: str = "done") -> None:
    """记录/更新每日任务的完成状态。"""
    user_pk = _ensure_user_pk(user_id)
    db.execute(
        """
        INSERT INTO daily_task_completions (user_id, task_date, task_id, status, completed_at)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id, task_date, task_id) DO UPDATE SET
            status = EXCLUDED.status,
            completed_at = CURRENT_TIMESTAMP
        """,
        (user_pk, task_date, task_id, status),
    )


def get_daily_task_completions(user_id: str, task_date: str) -> dict[str, str]:
    user_pk = _ensure_user_pk(user_id)
    rows = db.fetch_all(
        "SELECT task_id, status FROM daily_task_completions WHERE user_id = %s AND task_date = %s",
        (user_pk, task_date),
    )
    return {r["task_id"]: r["status"] for r in rows}


def delete_daily_task_completion(user_id: str, task_date: str, task_id: str) -> None:
    """删除一条每日任务完成记录(用户主动撤销完成时调用)。"""
    user_pk = _ensure_user_pk(user_id)
    db.execute(
        "DELETE FROM daily_task_completions WHERE user_id=%s AND task_date=%s AND task_id=%s",
        (user_pk, task_date, task_id),
    )


# ============================================================
# AI 对话历史 (DB 持久化,与 conversation_memory 双写)
# ============================================================
def insert_chat_message(user_id: str, role: str, content: str) -> None:
    user_pk = _ensure_user_pk(user_id)
    db.execute(
        "INSERT INTO chat_messages (user_id, role, content) VALUES (%s, %s, %s)",
        (user_pk, role, content),
    )


def get_chat_history(user_id: str, limit: int = 40) -> list[dict]:
    user_pk = _ensure_user_pk(user_id)
    rows = db.fetch_all(
        "SELECT id, role, content, created_at FROM chat_messages WHERE user_id = %s "
        "ORDER BY created_at DESC LIMIT %s",
        (user_pk, limit),
    )
    # 反转成时序正序
    return [
        {
            "id": int(r.get("id") or 0),
            "role": r["role"],
            "content": r["content"],
            "created_at": str(r.get("created_at", "")),
        }
        for r in reversed(rows)
    ]


def clear_chat_history(user_id: str) -> int:
    """清空某用户全部 chat_messages,返回删除条数。"""
    user_pk = _ensure_user_pk(user_id)
    return db.execute(
        "DELETE FROM chat_messages WHERE user_id = %s",
        (user_pk,),
    )


def delete_chat_message(user_id: str, message_id: int) -> int:
    """删除某用户指定 id 的 chat_message,只能删自己的(返回 0/1)。"""
    if not message_id or message_id <= 0:
        return 0
    user_pk = _ensure_user_pk(user_id)
    return db.execute(
        "DELETE FROM chat_messages WHERE id = %s AND user_id = %s",
        (int(message_id), user_pk),
    )


def get_answer_records_heatmap(user_id: str, days: int = 90) -> dict[str, int]:
    """返回最近 N 天每天的答题数 {"YYYY-MM-DD": count, ...},含 0 天的也要有 key(用于日历渲染)。"""
    user_pk = _ensure_user_pk(user_id)
    rows = db.fetch_all(
        """
        SELECT DATE(created_at) AS d, COUNT(*) AS c
          FROM answer_records
         WHERE user_id = %s
           AND created_at >= CURRENT_TIMESTAMP - (%s || ' days')::INTERVAL
         GROUP BY DATE(created_at)
         ORDER BY d ASC
        """,
        (user_pk, int(days)),
    )
    return {str(r["d"]): int(r["c"]) for r in rows}


# ============================================================
# 学习计划（按 user 持久化到 PG）
# ============================================================
def upsert_study_plan(user_id: str, plan: dict) -> None:
    """把整个 plan 写到 study_plans.plan(JSONB),按 user_id 一份。"""
    user_pk = _ensure_user_pk(user_id)
    db.execute(
        """
        INSERT INTO study_plans (user_id, plan, updated_at)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE
        SET plan = EXCLUDED.plan, updated_at = CURRENT_TIMESTAMP
        """,
        (user_pk, json.dumps(plan, ensure_ascii=False, default=str)),
    )


def get_study_plan(user_id: str) -> dict | None:
    user_pk = _ensure_user_pk(user_id)
    row = db.fetch_one(
        "SELECT plan, updated_at FROM study_plans WHERE user_id = %s",
        (user_pk,),
    )
    if not row:
        return None
    p = row.get("plan")
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except Exception:
            return None
    if isinstance(p, dict):
        p["_db_updated_at"] = str(row.get("updated_at", ""))
    return p


# ============================================================
# 兜底：JSON 备份（兼容旧的本地 JSON 文件）
# ============================================================
def load_state_with_fallback(user_id: str, data_dir: Path) -> dict[str, Any]:
    """先尝试 PG，失败时回退到 JSON。"""
    try:
        return load_state(user_id)
    except Exception:
        # 回退：原 JSON 行为
        from kaoyan_ai.utils.jsonl import load_jsonl  # noqa
        path = data_dir / "users" / f"{user_id}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"user_id": user_id}
