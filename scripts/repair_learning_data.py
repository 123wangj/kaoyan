from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
QUESTION_PATH = ROOT / "data" / "question_bank.jsonl"
KNOWLEDGE_PATH = ROOT / "data" / "knowledge_points.jsonl"
QUESTION_BACKUP = ROOT / "data" / "question_bank.before_system_repair.jsonl"
KNOWLEDGE_BACKUP = ROOT / "data" / "knowledge_points.before_system_repair.jsonl"
MANIFEST_PATH = ROOT / "data" / "learning_data_repair_manifest.json"
USERS_DIR = ROOT / "data" / "users"
USERS_BACKUP_DIR = ROOT / "data" / "users.before_system_repair"

SUBJECT_CODES = {
    "数据结构": "ds",
    "计算机组成原理": "co",
    "操作系统": "os",
    "计算机网络": "cn",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".repair.tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def normalize(value: object) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").lower())


def unique_list(values: list[Any]) -> list[Any]:
    result = []
    seen = set()
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if marker not in seen:
            seen.add(marker)
            result.append(value)
    return result


def merge_knowledge(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row.get("subject") or ""), normalize(row.get("title")))].append(row)

    merged_rows = []
    id_redirect: dict[str, str] = {}
    for group in groups.values():
        canonical = max(
            group,
            key=lambda row: (
                len(row.get("exam_questions") or []),
                len(str(row.get("detailed_explanation") or "")),
                len(str(row.get("content") or "")),
            ),
        )
        merged = dict(canonical)
        for field in ("knowledge_points", "score_points", "tags", "exam_questions"):
            merged[field] = unique_list(
                [item for row in group for item in (row.get(field) or [])]
            )
        longest_content = max(
            (str(row.get("content") or "") for row in group),
            key=len,
            default="",
        )
        longest_detail = max(
            (str(row.get("detailed_explanation") or "") for row in group),
            key=len,
            default="",
        )
        merged["content"] = longest_content
        merged["detailed_explanation"] = longest_detail
        merged["exam_count"] = len(merged.get("exam_questions") or [])
        merged_rows.append(merged)
        for row in group:
            id_redirect[str(row.get("id") or "")] = str(merged.get("id") or "")

    merged_rows.sort(
        key=lambda row: (
            list(SUBJECT_CODES).index(row.get("subject"))
            if row.get("subject") in SUBJECT_CODES
            else 99,
            int(row.get("chapter_order") or 999),
            str(row.get("id") or ""),
        )
    )
    return merged_rows, id_redirect


def question_duplicate_key(question: dict[str, Any]) -> tuple[Any, ...]:
    return (
        question.get("subject"),
        normalize(question.get("content") or question.get("title")),
        tuple(normalize(option) for option in (question.get("options") or [])),
        normalize(question.get("answer")),
    )


def remove_exact_question_duplicates(
    questions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for question in questions:
        groups[question_duplicate_key(question)].append(question)

    kept = []
    removed = []
    for group in groups.values():
        best = max(
            group,
            key=lambda question: (
                len(str(question.get("explanation") or "")),
                len(question.get("knowledge_points") or []),
                bool(question.get("image_url")),
            ),
        )
        kept.append(best)
        removed.extend(question for question in group if question is not best)
    return kept, removed


def make_unique_question_ids(
    questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    counts = Counter(str(question.get("id") or "") for question in questions)
    seen: Counter[str] = Counter()
    changes = []
    for question in questions:
        old_id = str(question.get("id") or "")
        seen[old_id] += 1
        if counts[old_id] <= 1 or seen[old_id] == 1:
            continue
        subject_code = SUBJECT_CODES.get(str(question.get("subject") or ""), "q")
        digest = hashlib.sha1(
            (
                str(question.get("subject") or "")
                + "|"
                + str(question.get("content") or "")
                + "|"
                + "|".join(str(x) for x in (question.get("options") or []))
            ).encode("utf-8")
        ).hexdigest()[:10]
        new_id = f"{old_id}--{subject_code}-{digest}"
        suffix = 2
        existing = {str(item.get("id") or "") for item in questions}
        while new_id in existing:
            new_id = f"{old_id}--{subject_code}-{digest}-{suffix}"
            suffix += 1
        question["id"] = new_id
        changes.append(
            {
                "old_id": old_id,
                "new_id": new_id,
                "subject": question.get("subject"),
                "content": question.get("content"),
            }
        )
    return changes


def ngrams(text: str, size: int = 2) -> set[str]:
    if len(text) <= size:
        return {text} if text else set()
    return {text[index : index + size] for index in range(len(text) - size + 1)}


def candidate_score(question_text: str, point: dict[str, Any]) -> float:
    title = normalize(point.get("title"))
    aliases = [
        normalize(value)
        for value in (
            (point.get("knowledge_points") or [])
            + (point.get("tags") or [])
            + (point.get("score_points") or [])
        )
        if normalize(value)
    ]
    score = 0.0
    if title and title in question_text:
        score += 12.0
    for alias in aliases:
        if len(alias) >= 2 and alias in question_text:
            score += min(7.0, 2.0 + len(alias) / 5)
    title_grams = ngrams(title)
    text_grams = ngrams(question_text)
    if title_grams:
        score += 5.0 * len(title_grams & text_grams) / len(title_grams)
    return score


def map_questions_to_knowledge(
    questions: list[dict[str, Any]],
    knowledge: list[dict[str, Any]],
) -> dict[str, int]:
    by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for point in knowledge:
        by_subject[str(point.get("subject") or "")].append(point)

    mapped_by_subject: Counter[str] = Counter()
    for question in questions:
        if question.get("knowledge_mapping_status") in {
            "pending_glm_review",
            "unmatched",
        }:
            continue
        subject = str(question.get("subject") or "")
        candidates = by_subject.get(subject, [])
        chapter_match = re.search(r"第\s*(\d+)\s*章", str(question.get("chapter") or ""))
        if chapter_match:
            chapter_order = int(chapter_match.group(1))
            chapter_candidates = [
                point
                for point in candidates
                if int(point.get("chapter_order") or 0) == chapter_order
            ]
            if chapter_candidates:
                candidates = chapter_candidates

        question_text = normalize(
            " ".join(
                [
                    str(question.get("content") or question.get("title") or ""),
                    str(question.get("explanation") or question.get("analysis") or ""),
                    " ".join(str(option) for option in (question.get("options") or [])),
                ]
            )
        )
        ranked = sorted(
            ((candidate_score(question_text, point), point) for point in candidates),
            key=lambda item: (item[0], len(str(item[1].get("title") or ""))),
            reverse=True,
        )
        if not ranked:
            question["knowledge_point_ids"] = []
            question["knowledge_points"] = []
            continue

        selected = [ranked[0][1]]
        if len(ranked) > 1 and ranked[1][0] >= max(5.0, ranked[0][0] * 0.78):
            selected.append(ranked[1][1])
        question["knowledge_point_ids"] = [point["id"] for point in selected]
        question["knowledge_points"] = [point["title"] for point in selected]
        question["knowledge_detail"] = (
            selected[0].get("detailed_explanation")
            or selected[0].get("content")
            or ""
        )
        question["knowledge_enriched_by"] = "offline_curriculum_mapping"
        mapped_by_subject[subject] += 1
    return dict(mapped_by_subject)


def add_knowledge_relationships(rows: list[dict[str, Any]]) -> None:
    by_chapter: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_title = {
        (str(row.get("subject") or ""), normalize(row.get("title"))): row
        for row in rows
    }
    for row in rows:
        by_chapter[
            (str(row.get("subject") or ""), str(row.get("chapter_id") or ""))
        ].append(row)
    for points in by_chapter.values():
        points.sort(key=lambda row: str(row.get("id") or ""))
        for index, point in enumerate(points):
            point["prerequisite_ids"] = [points[index - 1]["id"]] if index else []
            related = []
            if index:
                related.append(points[index - 1]["id"])
            if index + 1 < len(points):
                related.append(points[index + 1]["id"])
            point["related_point_ids"] = related
            point.setdefault("cross_subject_point_ids", [])

    curated_links = [
        (("操作系统", "虚拟内存"), ("计算机组成原理", "虚拟存储器")),
        (("操作系统", "内核态与用户态"), ("计算机组成原理", "中断系统")),
        (("操作系统", "进程与线程"), ("计算机组成原理", "流水线技术")),
        (("计算机网络", "滑动窗口"), ("数据结构", "队列")),
        (("计算机网络", "差错检测"), ("计算机组成原理", "校验码")),
    ]
    for left, right in curated_links:
        left_point = next(
            (
                row
                for (subject, title), row in by_title.items()
                if subject == left[0] and normalize(left[1]) in title
            ),
            None,
        )
        right_point = next(
            (
                row
                for (subject, title), row in by_title.items()
                if subject == right[0] and normalize(right[1]) in title
            ),
            None,
        )
        if left_point and right_point:
            left_point["cross_subject_point_ids"] = unique_list(
                left_point.get("cross_subject_point_ids", []) + [right_point["id"]]
            )
            right_point["cross_subject_point_ids"] = unique_list(
                right_point.get("cross_subject_point_ids", []) + [left_point["id"]]
            )


def canonical_knowledge_title(
    raw_title: object,
    subject: object,
    knowledge: list[dict[str, Any]],
) -> str:
    raw = str(raw_title or "").strip()
    subject_name = str(subject or "").strip()
    if not raw:
        return raw
    same_subject = [
        row for row in knowledge if str(row.get("subject") or "") == subject_name
    ]
    exact = next(
        (row for row in same_subject if str(row.get("title") or "") == raw),
        None,
    )
    if exact:
        return str(exact["title"])
    alias = next(
        (
            row
            for row in same_subject
            if raw in (row.get("knowledge_points") or [])
            or raw in (row.get("tags") or [])
        ),
        None,
    )
    if alias:
        return str(alias["title"])
    contained = next(
        (
            row
            for row in same_subject
            if raw in str(row.get("title") or "")
            or str(row.get("title") or "") in raw
        ),
        None,
    )
    return str(contained["title"]) if contained else raw


def repair_user_states(knowledge: list[dict[str, Any]]) -> dict[str, int]:
    if not USERS_DIR.exists():
        return {"files": 0, "mastery_entries": 0}
    if not USERS_BACKUP_DIR.exists():
        shutil.copytree(USERS_DIR, USERS_BACKUP_DIR)

    repaired_files = 0
    mastery_entries = 0
    for path in sorted(USERS_DIR.glob("*.json")):
        state = json.loads(path.read_text(encoding="utf-8"))
        mastery: dict[str, dict[str, Any]] = {}
        for title, item in (state.get("mastery") or {}).items():
            subject = item.get("subject", "")
            canonical = canonical_knowledge_title(title, subject, knowledge)
            target = mastery.setdefault(
                canonical,
                {
                    "subject": subject,
                    "attempts": 0,
                    "correct": 0,
                    "wrong": 0,
                },
            )
            attempts = int(item.get("attempts", 0))
            correct = int(item.get("correct", 0))
            # Alias and canonical rows can represent the same persisted
            # attempt after a legacy PG/JSON merge, so keep the strongest
            # counters instead of double-counting them.
            target["attempts"] = max(target["attempts"], attempts)
            target["correct"] = max(target["correct"], correct)
            target["wrong"] = max(
                target["wrong"],
                int(item.get("wrong", max(0, attempts - correct))),
            )
            if item.get("last_answered_at"):
                target["last_answered_at"] = max(
                    str(target.get("last_answered_at") or ""),
                    str(item["last_answered_at"]),
                )

        for item in mastery.values():
            item["score"] = max(
                0.0,
                min(
                    100.0,
                    55.0 + item["correct"] * 10.0 - item["wrong"] * 18.0,
                ),
            )
            score = item["score"]
            item["level"] = (
                "mastered"
                if score >= 85
                else "stable"
                if score >= 70
                else "weak"
                if score >= 50
                else "danger"
            )
        state["mastery"] = mastery

        for collection_name in ("answer_records", "wrong_questions"):
            for item in state.get(collection_name, []):
                item["knowledge_points"] = unique_list(
                    [
                        canonical_knowledge_title(
                            point, item.get("subject"), knowledge
                        )
                        for point in item.get("knowledge_points", [])
                    ]
                )
        for item in (state.get("wrong_book") or {}).values():
            item["knowledge_points"] = unique_list(
                [
                    canonical_knowledge_title(point, item.get("subject"), knowledge)
                    for point in item.get("knowledge_points", [])
                ]
            )

        path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        repaired_files += 1
        mastery_entries += len(mastery)
    return {"files": repaired_files, "mastery_entries": mastery_entries}


def main() -> None:
    if not QUESTION_BACKUP.exists():
        shutil.copy2(QUESTION_PATH, QUESTION_BACKUP)
    if not KNOWLEDGE_BACKUP.exists():
        shutil.copy2(KNOWLEDGE_PATH, KNOWLEDGE_BACKUP)

    original_questions = load_jsonl(QUESTION_PATH)
    original_knowledge = load_jsonl(KNOWLEDGE_PATH)
    knowledge, id_redirect = merge_knowledge(original_knowledge)
    add_knowledge_relationships(knowledge)
    questions, removed_questions = remove_exact_question_duplicates(original_questions)
    id_changes = make_unique_question_ids(questions)
    mapped_by_subject = map_questions_to_knowledge(questions, knowledge)
    repaired_user_states = repair_user_states(knowledge)

    write_jsonl(KNOWLEDGE_PATH, knowledge)
    write_jsonl(QUESTION_PATH, questions)

    manifest = {
        "questions_before": len(original_questions),
        "questions_after": len(questions),
        "exact_duplicate_questions_removed": len(removed_questions),
        "question_ids_changed": len(id_changes),
        "knowledge_before": len(original_knowledge),
        "knowledge_after": len(knowledge),
        "knowledge_duplicates_merged": len(original_knowledge) - len(knowledge),
        "mapped_by_subject": mapped_by_subject,
        "repaired_user_states": repaired_user_states,
        "id_changes": id_changes,
        "removed_questions": [
            {
                "id": question.get("id"),
                "subject": question.get("subject"),
                "content": question.get("content"),
            }
            for question in removed_questions
        ],
        "knowledge_id_redirect": id_redirect,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in manifest.items() if not isinstance(value, (list, dict))}, ensure_ascii=False))
    print("mapped_by_subject", mapped_by_subject)


if __name__ == "__main__":
    main()
