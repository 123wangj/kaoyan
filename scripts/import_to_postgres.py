"""将现有 JSONL / JSON 数据导入 PostgreSQL。

使用方式:
    # 1. 先确保 PostgreSQL 已建好 kaoyan_ai 库，并执行过 db/init.sql
    # 2. 配置 .env 中的 DB_* 变量
    # 3. 在项目根目录执行:
    python -m scripts.import_to_postgres

可选参数:
    --skip-questions   跳过题库导入
    --skip-users       跳过用户数据导入
    --skip-kps         跳过知识点导入
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 让脚本可以 import kaoyan_ai
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import psycopg2.extras

from kaoyan_ai import db  # noqa: E402


# ============================================================
# 科目名 -> code 映射（与 init.sql 中插入的 subjects 对应）
# ============================================================
SUBJECT_NAME2CODE = {
    "数据结构": "DS",
    "DS": "DS",
    "操作系统": "OS",
    "OS": "OS",
    "计算机网络": "CN",
    "计算机网络 ": "CN",
    "CN": "CN",
    "计算机组成原理": "CO",
    "组成原理": "CO",
    "CO": "CO",
}


def _subject_code(name: str | None) -> str | None:
    if not name:
        return None
    return SUBJECT_NAME2CODE.get(name.strip())


def _load_jsonl(path: Path) -> list[dict]:
    """读取 jsonl 文件，忽略空行与解析错误。"""
    if not path.exists():
        return []
    items: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


# ============================================================
# 1. 题库导入
# ============================================================
def import_questions(jsonl_path: Path) -> int:
    rows = _load_jsonl(jsonl_path)
    if not rows:
        print(f"  [skip] {jsonl_path} 不存在或为空")
        return 0

    # 拿 subject_code -> subject_id
    subjects = db.fetch_all("SELECT id, code FROM subjects")
    code2id = {s["code"]: s["id"] for s in subjects}

    inserted = 0
    with db.get_conn() as conn:
        cur = conn.cursor()
        for q in rows:
            subject_id = code2id.get(_subject_code(q.get("subject")) or "")
            options = q.get("options")
            # options 可能是 list 也可能是 dict，统一存成 dict
            if isinstance(options, list):
                opts_dict = {chr(ord("A") + i): v for i, v in enumerate(options)}
            else:
                opts_dict = options

            cur.execute(
                """
                INSERT INTO questions (
                    external_id, subject_id, question_type, stem, options,
                    answer, analysis, difficulty, source, is_real_exam,
                    chapter, section, question_number
                ) VALUES (
                    %(external_id)s, %(subject_id)s, %(question_type)s, %(stem)s, %(options)s,
                    %(answer)s, %(analysis)s, %(difficulty)s, %(source)s, %(is_real_exam)s,
                    %(chapter)s, %(section)s, %(question_number)s
                )
                ON CONFLICT (external_id) DO UPDATE SET
                    subject_id      = EXCLUDED.subject_id,
                    question_type   = EXCLUDED.question_type,
                    stem            = EXCLUDED.stem,
                    options         = EXCLUDED.options,
                    answer          = EXCLUDED.answer,
                    analysis        = EXCLUDED.analysis,
                    difficulty      = EXCLUDED.difficulty,
                    source          = EXCLUDED.source,
                    is_real_exam    = EXCLUDED.is_real_exam,
                    chapter         = EXCLUDED.chapter,
                    section         = EXCLUDED.section,
                    question_number = EXCLUDED.question_number
                """,
                {
                    "external_id": q.get("id"),
                    "subject_id": subject_id,
                    "question_type": q.get("type", "choice"),
                    "stem": q.get("content") or q.get("stem") or "",
                    "options": psycopg2.extras.Json(opts_dict) if opts_dict else None,
                    "answer": q.get("answer"),
                    "analysis": q.get("explanation") or q.get("analysis"),
                    "difficulty": q.get("difficulty", "基础"),
                    "source": q.get("source"),
                    "is_real_exam": q.get("is_real_exam", False),
                    "chapter": q.get("chapter"),
                    "section": q.get("section"),
                    "question_number": str(q.get("question_number")) if q.get("question_number") else None,
                },
            )
            inserted += 1
        conn.commit()
    print(f"  [ok] questions: {inserted} 条 (来自 {jsonl_path.name})")
    return inserted


# ============================================================
# 2. 知识点导入
# ============================================================
def import_knowledge_points(jsonl_path: Path) -> int:
    rows = _load_jsonl(jsonl_path)
    if not rows:
        print(f"  [skip] {jsonl_path} 不存在或为空")
        return 0

    subjects = db.fetch_all("SELECT id, code FROM subjects")
    code2id = {s["code"]: s["id"] for s in subjects}

    inserted = 0
    with db.get_conn() as conn:
        cur = conn.cursor()
        for kp in rows:
            code = _subject_code(kp.get("subject"))
            subject_id = code2id.get(code) if code else None
            cur.execute(
                """
                INSERT INTO knowledge_points (subject_id, name, chapter, description)
                VALUES (%(subject_id)s, %(name)s, %(chapter)s, %(description)s)
                ON CONFLICT (subject_id, name, chapter) DO UPDATE SET
                    description = EXCLUDED.description
                """,
                {
                    "subject_id": subject_id,
                    "name": kp.get("title") or kp.get("name") or "",
                    "chapter": kp.get("chapter_title") or kp.get("chapter"),
                    "description": kp.get("content") or kp.get("description"),
                },
            )
            inserted += 1
        conn.commit()
    print(f"  [ok] knowledge_points: {inserted} 条")
    return inserted


def import_question_knowledge_links(question_path: Path, knowledge_path: Path) -> int:
    """Rebuild links for the active question bank using canonical curriculum IDs."""
    questions = _load_jsonl(question_path)
    knowledge = _load_jsonl(knowledge_path)
    if not questions or not knowledge:
        print("  [skip] question_kp: active question bank or curriculum is empty")
        return 0

    kp_by_external_id = {
        str(kp.get("id")): kp
        for kp in knowledge
        if kp.get("id") and (kp.get("title") or kp.get("name"))
    }
    inserted = 0
    with db.get_conn() as conn:
        cur = conn.cursor()
        active_ids = [str(q["id"]) for q in questions if q.get("id")]
        cur.execute(
            """
            DELETE FROM question_kp qkp
            USING questions q
            WHERE q.id = qkp.question_id
              AND q.external_id = ANY(%s)
            """,
            (active_ids,),
        )

        for question in questions:
            external_id = str(question.get("id") or "")
            if not external_id:
                continue
            for kp_external_id in question.get("knowledge_point_ids") or []:
                kp = kp_by_external_id.get(str(kp_external_id))
                if not kp:
                    continue
                subject_code = _subject_code(kp.get("subject"))
                name = kp.get("title") or kp.get("name")
                chapter = kp.get("chapter_title") or kp.get("chapter")
                cur.execute(
                    """
                    INSERT INTO question_kp (question_id, knowledge_point_id)
                    SELECT q.id, kp.id
                    FROM questions q
                    JOIN knowledge_points kp ON kp.name = %s
                    JOIN subjects s ON s.id = kp.subject_id AND s.code = %s
                    WHERE q.external_id = %s
                      AND kp.chapter IS NOT DISTINCT FROM %s
                    ORDER BY kp.id
                    LIMIT 1
                    ON CONFLICT DO NOTHING
                    """,
                    (name, subject_code, external_id, chapter),
                )
                inserted += cur.rowcount
        conn.commit()
    print(f"  [ok] question_kp: {inserted}")
    return inserted


# ============================================================
# 3. 用户 + 做题记录 + 错题本 + 推送历史
# ============================================================
def _get_or_create_user(profile: dict) -> int:
    """根据 u1.json 的 user_id 字段创建用户，返回 users.id。"""
    user_id = profile["user_id"]
    db.execute(
        """
        INSERT INTO users (user_id, nickname, target_school, target_major, exam_date)
        VALUES (%(uid)s, %(nick)s, %(school)s, %(major)s, %(exam)s)
        ON CONFLICT (user_id) DO UPDATE SET
            target_school = EXCLUDED.target_school,
            target_major  = EXCLUDED.target_major,
            exam_date     = EXCLUDED.exam_date
        RETURNING id
        """,
        {
            "uid": user_id,
            "nick": profile.get("nickname") or user_id,
            "school": profile.get("target_school"),
            "major": profile.get("target_major"),
            "exam": profile.get("exam_date"),
        },
    )
    row = db.fetch_one("SELECT id FROM users WHERE user_id = %s", (user_id,))
    return int(row["id"])


def _external_id_to_question_id(ext_id: str) -> int | None:
    row = db.fetch_one("SELECT id FROM questions WHERE external_id = %s", (ext_id,))
    return int(row["id"]) if row else None


def import_user_profile(profile_path: Path) -> None:
    if not profile_path.exists():
        print(f"  [skip] {profile_path} 不存在")
        return

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    user_pk = _get_or_create_user(profile)
    print(f"  [ok] user: {profile.get('user_id')} -> id={user_pk}")

    # 3.1 做题记录
    ar_count = 0
    for ar in profile.get("answer_records", []):
        qid = _external_id_to_question_id(ar.get("question_id", ""))
        if not qid:
            continue
        db.execute(
            """
            INSERT INTO answer_records (
                user_id, question_id, is_correct, spent_seconds, created_at
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                user_pk,
                qid,
                bool(ar.get("is_correct")),
                ar.get("spent_seconds"),
                ar.get("created_at"),
            ),
        )
        ar_count += 1
    print(f"  [ok] answer_records: {ar_count} 条")

    # 3.2 错题本
    wq_count = 0
    for wq in profile.get("wrong_questions", []):
        qid = _external_id_to_question_id(wq.get("question_id", ""))
        if not qid:
            continue
        db.execute(
            """
            INSERT INTO wrong_questions (user_id, question_id, error_count, last_error_at, notes)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, question_id) DO NOTHING
            """,
            (
                user_pk,
                qid,
                wq.get("error_count", 1),
                wq.get("created_at"),
                wq.get("error_reason"),
            ),
        )
        wq_count += 1
    print(f"  [ok] wrong_questions: {wq_count} 条")

    # 3.3 推送历史
    ph_count = 0
    for kp_id in profile.get("pushed_knowledge_ids", []):
        db.execute(
            """
            INSERT INTO push_history (user_id, item_type, item_id, pushed_at)
            VALUES (%s, 'knowledge', %s, CURRENT_TIMESTAMP)
            ON CONFLICT DO NOTHING
            """,
            (user_pk, kp_id),
        )
        ph_count += 1
    for q_id in profile.get("pushed_question_ids", []):
        db.execute(
            """
            INSERT INTO push_history (user_id, item_type, item_id, pushed_at)
            VALUES (%s, 'question', %s, CURRENT_TIMESTAMP)
            ON CONFLICT DO NOTHING
            """,
            (user_pk, q_id),
        )
        ph_count += 1
    print(f"  [ok] push_history: {ph_count} 条")


# ============================================================
# Main
# ============================================================
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-questions", action="store_true")
    parser.add_argument("--skip-users", action="store_true")
    parser.add_argument("--skip-kps", action="store_true")
    args = parser.parse_args()

    # 初始化连接池（这里会触发 psycopg2 实际连接 PG）
    try:
        db.init_pool()
    except Exception as e:
        print(f"[fatal] 连接 PostgreSQL 失败: {e}")
        print("  请检查 .env 中的 DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD")
        print("  以及是否已执行 db/init.sql")
        sys.exit(1)

    data_dir = Path(os.environ.get("DATA_DIR", "data"))

    print("=== 开始导入 ===")
    if not args.skip_kps:
        import_knowledge_points(data_dir / "knowledge_points.jsonl")
    if not args.skip_questions:
        active_question_path = data_dir / "question_bank.jsonl"
        import_questions(active_question_path)
        if not args.skip_kps:
            import_question_knowledge_links(
                active_question_path,
                data_dir / "knowledge_points.jsonl",
            )
    if not args.skip_users:
        users_dir = data_dir / "users"
        if users_dir.exists():
            for f in sorted(users_dir.glob("*.json")):
                print(f"-- user profile: {f.name} --")
                import_user_profile(f)

    print("=== 导入完成 ===")


if __name__ == "__main__":
    main()
