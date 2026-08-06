from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import shutil
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from kaoyan_ai.agents.base import LLMClient
from kaoyan_ai.config import get_settings
from scripts.repair_learning_data import candidate_score, normalize


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
QUESTION_PATH = DATA_DIR / "question_bank.jsonl"
KNOWLEDGE_PATH = DATA_DIR / "knowledge_points.jsonl"
QUEUE_PATH = DATA_DIR / "knowledge_mapping_review_queue.jsonl"
RESULT_PATH = DATA_DIR / "knowledge_mapping_glm_results.jsonl"
PROPOSAL_PATH = DATA_DIR / "knowledge_point_proposals.json"
QUESTION_BACKUP = DATA_DIR / "question_bank.before_glm_mapping.jsonl"
KNOWLEDGE_EXPANSION_BACKUP = DATA_DIR / "knowledge_points.before_glm_expansion.jsonl"
ACCEPTANCE_THRESHOLD = 0.82
NEW_POINT_MIN_SUPPORT = 1


SYSTEM_PROMPT = """你是考研 408 题目知识点审核员。你的首要目标是准确，不是覆盖率。
只能从每道题自己的 candidates 中选择知识点 ID。
如果候选知识点没有直接、明确、核心地覆盖题目考点，必须返回 unmatched，绝对不要因为科目或章节相同而强行匹配。
宽泛上位概念、相邻概念、仅在解析中顺带出现的概念，都不能作为匹配依据。
一道题可以匹配 1 到 3 个真正独立考查的知识点；不要为了凑数增加标签。
只有 candidates 确实缺少核心考点时，才填写 missing_concept。
严格返回 JSON 数组，不要 Markdown，不要额外说明。每项格式：
{"question_id":"...","status":"matched|unmatched","knowledge_point_ids":[],"confidence":0.0,"evidence":"题干或解析中的简短依据","missing_concept":"","missing_concept_definition":""}
"""

PROPOSAL_SYSTEM_PROMPT = """你是考研 408 知识体系架构师。请分析无法归入现有知识点的题目，准确识别每道题实际考查的核心知识点。
要求：
1. 先与 existing_points 做语义比对；只有现有知识点直接覆盖题目核心考点时，才返回 existing_point。
2. 如果现有知识点没有直接覆盖，必须返回 new_point 并创建边界清晰的新知识点，不能为了减少新增而硬匹配。
2. 同义表达、缩写、上下文不同但本质相同的概念应聚为一个提案，不要求来自同一章节。
3. 仅仅相关、前后置或同章的不同概念不能合并。
4. 单道题确认考查独立概念时也应创建；多道题的同义概念必须合并为一个新知识点。
5. 每个 question_id 必须且只能出现在一个结果中。只有题干损坏到无法识别考点时才返回 defer。
6. 严格输出 JSON 数组，不要 Markdown。每项格式：
{"decision":"new_point|existing_point|defer","title":"规范知识点名","description":"边界清晰的定义","support_question_ids":[],"existing_point_ids":[],"related_existing_ids":[],"confidence":0.0,"reason":"判断依据"}
"""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def chapter_candidates(
    question: dict[str, Any],
    by_subject: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    candidates = list(by_subject.get(str(question.get("subject") or ""), []))
    match = re.search(r"第\s*(\d+)\s*章", str(question.get("chapter") or ""))
    if not match:
        return candidates
    chapter_order = int(match.group(1))
    same_chapter = [
        point
        for point in candidates
        if int(point.get("chapter_order") or 0) == chapter_order
    ]
    return same_chapter or candidates


def question_text(question: dict[str, Any]) -> str:
    return "\n".join(
        [
            str(question.get("content") or question.get("title") or ""),
            "\n".join(str(option) for option in question.get("options") or []),
            str(question.get("explanation") or question.get("analysis") or ""),
        ]
    ).strip()


def heuristic_confidence(
    question: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> tuple[str, float, float]:
    text = normalize(question_text(question))
    ranked = sorted(
        (candidate_score(text, point) for point in candidates),
        reverse=True,
    )
    top = ranked[0] if ranked else 0.0
    second = ranked[1] if len(ranked) > 1 else 0.0
    margin = top - second
    if top >= 10 and margin >= 2:
        return "high", top, margin
    if top >= 5 and margin >= 1:
        return "medium", top, margin
    return "low", top, margin


def build_review_queue(
    questions: list[dict[str, Any]],
    knowledge: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for point in knowledge:
        by_subject[str(point.get("subject") or "")].append(point)

    queue = []
    for question in questions:
        candidates = chapter_candidates(question, by_subject)
        level, score, margin = heuristic_confidence(question, candidates)
        if level != "low":
            continue
        queue.append(
            {
                "question_id": str(question.get("id") or ""),
                "subject": question.get("subject"),
                "chapter": question.get("chapter"),
                "question": question_text(question),
                "current_mapping": question.get("knowledge_point_ids") or [],
                "heuristic_score": round(score, 3),
                "heuristic_margin": round(margin, 3),
                "candidates": [
                    {
                        "id": point.get("id"),
                        "title": point.get("title"),
                        "aliases": point.get("knowledge_points") or [],
                        "tags": point.get("tags") or [],
                        "summary": str(point.get("content") or "")[:240],
                    }
                    for point in candidates
                ],
            }
        )
    return queue


def extract_json_array(text: str) -> list[dict[str, Any]]:
    match = re.search(r"\[[\s\S]*\]", text or "")
    if not match:
        return []
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def validate_model_result(
    raw: dict[str, Any],
    task: dict[str, Any],
    threshold: float = ACCEPTANCE_THRESHOLD,
) -> dict[str, Any]:
    allowed_ids = {str(item.get("id") or "") for item in task.get("candidates", [])}
    returned_ids = list(
        dict.fromkeys(
            str(item).strip()
            for item in (raw.get("knowledge_point_ids") or [])
            if str(item).strip()
        )
    )
    try:
        confidence = float(raw.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    evidence = str(raw.get("evidence") or "").strip()
    requested_status = str(raw.get("status") or "").strip().lower()
    ids_are_valid = bool(returned_ids) and len(returned_ids) <= 3 and set(returned_ids) <= allowed_ids
    accepted = (
        requested_status == "matched"
        and confidence >= threshold
        and ids_are_valid
        and len(evidence) >= 4
    )
    return {
        "question_id": task["question_id"],
        "status": "matched" if accepted else "unmatched",
        "knowledge_point_ids": returned_ids if accepted else [],
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "evidence": evidence,
        "missing_concept": str(raw.get("missing_concept") or "").strip() if not accepted else "",
        "missing_concept_definition": (
            str(raw.get("missing_concept_definition") or "").strip() if not accepted else ""
        ),
        "validation": {
            "requested_status": requested_status,
            "ids_are_valid": ids_are_valid,
            "threshold": threshold,
            "accepted": accepted,
        },
        "subject": task.get("subject"),
        "chapter": task.get("chapter"),
    }


def _classify_batch(
    batch: list[dict[str, Any]],
    batch_number: int,
) -> list[dict[str, Any]]:
    client = LLMClient()
    user_prompt = json.dumps(batch, ensure_ascii=False)
    expected_ids = {task["question_id"] for task in batch}
    raw_by_id: dict[str, dict[str, Any]] = {}
    max_attempts = 8
    for attempt in range(1, max_attempts + 1):
        response = client.generate(SYSTEM_PROMPT, user_prompt)
        if response.startswith("大模型服务暂时不可用"):
            error_line = next(
                (
                    line
                    for line in response.splitlines()
                    if line.startswith("错误类型")
                ),
                "模型服务错误",
            )
            print(
                f"batch {batch_number}, attempt {attempt}/{max_attempts}: {error_line}",
                flush=True,
            )
            time.sleep(min(60, 10 * attempt))
            continue
        raw_rows = extract_json_array(response)
        raw_by_id = {
            str(row.get("question_id") or ""): row
            for row in raw_rows
            if isinstance(row, dict)
        }
        missing_ids = expected_ids - set(raw_by_id)
        if not missing_ids:
            break
        print(
            f"incomplete batch {batch_number}, attempt {attempt}/{max_attempts}, "
            f"missing={len(missing_ids)}",
            flush=True,
        )
        time.sleep(min(60, 10 * attempt))
    if expected_ids - set(raw_by_id):
        raise RuntimeError(
            f"GLM 返回不完整，批次 {batch_number} 未写入结果；可稍后安全续跑。"
        )
    return [
        validate_model_result(raw_by_id[task["question_id"]], task)
        for task in batch
    ]


def classify_queue(
    queue: list[dict[str, Any]],
    batch_size: int,
    workers: int = 1,
) -> list[dict[str, Any]]:
    settings = get_settings()
    if settings.llm_provider.lower() != "glm" or not settings.glm_api_key:
        raise RuntimeError(
            "GLM-5.2 已配置，但 GLM_API_KEY 为空；未调用模型，也未改写任何题目。"
        )
    completed = {
        row.get("question_id"): row
        for row in load_jsonl(RESULT_PATH)
        if row.get("question_id")
    }
    pending = [task for task in queue if task["question_id"] not in completed]
    batches = [
        pending[start : start + batch_size]
        for start in range(0, len(pending), batch_size)
    ]
    processed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_to_number = {
            executor.submit(_classify_batch, batch, number): number
            for number, batch in enumerate(batches, 1)
        }
        for future in concurrent.futures.as_completed(future_to_number):
            rows = future.result()
            for row in rows:
                completed[row["question_id"]] = row
            processed += len(rows)
            write_jsonl(RESULT_PATH, list(completed.values()))
            print(
                f"classified {processed}/{len(pending)} "
                f"(total saved={len(completed)})",
                flush=True,
            )
    return list(completed.values())


def stage_review_queue(
    questions: list[dict[str, Any]],
    queue: list[dict[str, Any]],
) -> int:
    if not QUESTION_BACKUP.exists():
        shutil.copy2(QUESTION_PATH, QUESTION_BACKUP)
    queued = {row["question_id"]: row for row in queue}
    staged = 0
    for question in questions:
        task = queued.get(str(question.get("id") or ""))
        if not task:
            continue
        if question.get("knowledge_mapping_status") != "pending_glm_review":
            question["provisional_knowledge_point_ids"] = list(
                question.get("knowledge_point_ids") or []
            )
            question["provisional_knowledge_points"] = list(
                question.get("knowledge_points") or []
            )
        question["knowledge_point_ids"] = []
        question["knowledge_points"] = []
        question["knowledge_mapping_status"] = "pending_glm_review"
        question["knowledge_mapping_confidence"] = None
        question["knowledge_mapping_heuristic_score"] = task["heuristic_score"]
        question["knowledge_mapping_heuristic_margin"] = task["heuristic_margin"]
        staged += 1
    write_jsonl(QUESTION_PATH, questions)
    return staged


def apply_verified_mappings(
    questions: list[dict[str, Any]],
    knowledge: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> dict[str, int]:
    if not QUESTION_BACKUP.exists():
        shutil.copy2(QUESTION_PATH, QUESTION_BACKUP)
    knowledge_by_id = {str(point["id"]): point for point in knowledge}
    result_by_id = {str(row["question_id"]): row for row in results}
    counts: Counter[str] = Counter()
    for question in questions:
        result = result_by_id.get(str(question.get("id") or ""))
        if not result:
            continue
        previous_ids = list(question.get("knowledge_point_ids") or [])
        if result.get("status") == "matched":
            ids = [
                point_id
                for point_id in result.get("knowledge_point_ids") or []
                if point_id in knowledge_by_id
            ]
            question["knowledge_point_ids"] = ids
            question["knowledge_points"] = [knowledge_by_id[point_id]["title"] for point_id in ids]
            question["knowledge_mapping_status"] = "glm_verified"
            question["knowledge_mapping_confidence"] = result.get("confidence")
            question["knowledge_mapping_evidence"] = result.get("evidence")
            counts["matched"] += 1
        else:
            # Preserve the old guess only as audit metadata. It is no longer an
            # authoritative mapping and must not feed personalization.
            question["provisional_knowledge_point_ids"] = previous_ids
            question["knowledge_point_ids"] = []
            question["knowledge_points"] = []
            question["knowledge_mapping_status"] = "unmatched"
            question["knowledge_mapping_confidence"] = result.get("confidence", 0)
            counts["unmatched"] += 1
    write_jsonl(QUESTION_PATH, questions)
    return dict(counts)


def proposal_groups(
    results: list[dict[str, Any]],
    min_support: int = NEW_POINT_MIN_SUPPORT,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        if row.get("status") != "unmatched":
            continue
        concept = str(row.get("missing_concept") or "").strip()
        normalized = normalize(concept)
        if len(normalized) < 2:
            continue
        key = (str(row.get("subject") or ""), str(row.get("chapter") or ""), normalized)
        groups[key].append(row)

    proposals = []
    for (subject, chapter, normalized), rows in groups.items():
        if len(rows) < min_support:
            continue
        concept = Counter(str(row.get("missing_concept") or "") for row in rows).most_common(1)[0][0]
        definition = max(
            (str(row.get("missing_concept_definition") or "") for row in rows),
            key=len,
            default="",
        )
        digest = hashlib.sha1(f"{subject}|{chapter}|{normalized}".encode("utf-8")).hexdigest()[:10]
        proposals.append(
            {
                "proposal_id": f"kp-proposal-{digest}",
                "subject": subject,
                "chapter": chapter,
                "title": concept,
                "description": definition,
                "support_count": len(rows),
                "question_ids": [row["question_id"] for row in rows],
                "status": "needs_review",
                "note": "仅为多题共同缺口提案；人工确认与去重后才可写入正式知识点库。",
            }
        )
    return sorted(proposals, key=lambda row: row["support_count"], reverse=True)


def semantic_proposal_groups(
    results: list[dict[str, Any]],
    knowledge: list[dict[str, Any]],
    queue: list[dict[str, Any]],
    min_support: int = 1,
    _retry_depth: int = 0,
) -> dict[str, list[dict[str, Any]]]:
    settings = get_settings()
    if settings.llm_provider.lower() != "glm" or not settings.glm_api_key:
        raise RuntimeError("缺少 GLM_API_KEY，无法执行新增知识点语义聚类。")

    task_by_id = {task["question_id"]: task for task in queue}
    existing_by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for point in knowledge:
        existing_by_subject[str(point.get("subject") or "")].append(point)
    unmatched_by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        if row.get("status") != "unmatched" or not row.get("missing_concept"):
            continue
        task = task_by_id.get(str(row.get("question_id") or ""), {})
        unmatched_by_subject[str(row.get("subject") or "")].append(
            {
                "question_id": row.get("question_id"),
                "chapter": row.get("chapter"),
                "missing_concept": row.get("missing_concept"),
                "definition": row.get("missing_concept_definition"),
                "evidence": row.get("evidence"),
                "question_excerpt": str(task.get("question") or "")[:420],
            }
        )

    client = LLMClient()
    proposals: list[dict[str, Any]] = []
    existing_matches: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    for subject, unmatched in unmatched_by_subject.items():
        existing = existing_by_subject.get(subject, [])
        payload = {
            "subject": subject,
            "existing_points": [
                {
                    "id": point.get("id"),
                    "title": point.get("title"),
                    "aliases": point.get("knowledge_points") or [],
                    "summary": str(point.get("content") or "")[:220],
                }
                for point in existing
            ],
            "unmatched_questions": unmatched,
        }
        response = client.generate(
            PROPOSAL_SYSTEM_PROMPT,
            json.dumps(payload, ensure_ascii=False),
        )
        raw_rows = extract_json_array(response)
        if not raw_rows and unmatched:
            raise RuntimeError(f"{subject} 的新增知识点语义聚类未返回有效 JSON。")

        allowed_question_ids = {
            str(item["question_id"]) for item in unmatched if item.get("question_id")
        }
        allowed_existing_ids = {
            str(point.get("id") or "") for point in existing if point.get("id")
        }
        existing_names = {
            normalize(value)
            for point in existing
            for value in [
                point.get("title"),
                *(point.get("knowledge_points") or []),
                *(point.get("tags") or []),
            ]
            if normalize(value)
        }
        covered_question_ids: set[str] = set()
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            decision = str(raw.get("decision") or "").strip()
            title = str(raw.get("title") or "").strip()
            title_key = normalize(title)
            support_ids = list(
                dict.fromkeys(
                    str(item)
                    for item in raw.get("support_question_ids") or []
                    if str(item) in allowed_question_ids
                )
            )
            if set(support_ids) & covered_question_ids:
                continue
            if not support_ids:
                continue
            covered_question_ids.update(support_ids)
            try:
                confidence = float(raw.get("confidence", 0))
            except (TypeError, ValueError):
                confidence = 0.0

            if decision == "existing_point":
                existing_ids = list(
                    dict.fromkeys(
                        str(item)
                        for item in raw.get("existing_point_ids") or []
                        if str(item) in allowed_existing_ids
                    )
                )
                if existing_ids and confidence >= ACCEPTANCE_THRESHOLD:
                    existing_matches.append(
                        {
                            "subject": subject,
                            "question_ids": support_ids,
                            "knowledge_point_ids": existing_ids[:3],
                            "confidence": round(confidence, 4),
                            "reason": str(raw.get("reason") or "").strip(),
                        }
                    )
                else:
                    deferred.append(
                        {
                            "subject": subject,
                            "question_ids": support_ids,
                            "reason": "existing_point 置信度不足或 ID 无效",
                        }
                    )
                continue

            if decision == "defer":
                deferred.append(
                    {
                        "subject": subject,
                        "question_ids": support_ids,
                        "reason": str(raw.get("reason") or "").strip(),
                    }
                )
                continue

            if decision != "new_point":
                deferred.append(
                    {
                        "subject": subject,
                        "question_ids": support_ids,
                        "reason": "模型返回了未知 decision",
                    }
                )
                continue

            if (
                len(title_key) < 2
                or len(support_ids) < min_support
                or title_key in existing_names
            ):
                deferred.append(
                    {
                        "subject": subject,
                        "question_ids": support_ids,
                        "reason": "新增知识点名称无效或与现有知识点重复",
                    }
                )
                continue
            related_ids = [
                str(item)
                for item in raw.get("related_existing_ids") or []
                if str(item) in allowed_existing_ids
            ]
            chapters = sorted(
                {
                    str(task_by_id[item].get("chapter") or "")
                    for item in support_ids
                    if item in task_by_id
                }
            )
            digest = hashlib.sha1(
                f"{subject}|{title_key}".encode("utf-8")
            ).hexdigest()[:10]
            proposals.append(
                {
                    "proposal_id": f"kp-proposal-{digest}",
                    "subject": subject,
                    "chapters": chapters,
                    "title": title,
                    "description": str(raw.get("description") or "").strip(),
                    "support_count": len(support_ids),
                    "question_ids": support_ids,
                    "related_existing_ids": related_ids,
                    "reason": str(raw.get("reason") or "").strip(),
                    "confidence": round(confidence, 4),
                    "status": "ready_to_create",
                    "note": "由 GLM 语义聚类产生；同义概念已合并，现有知识点无法直接覆盖。",
                }
            )
        missing_coverage = allowed_question_ids - covered_question_ids
        if missing_coverage:
            if _retry_depth >= 7:
                raise RuntimeError(
                    f"{subject} 的语义归类连续重试后仍遗漏 {len(missing_coverage)} 道题。"
                )
            print(
                f"semantic incomplete subject={subject}, retry={_retry_depth + 1}/7, "
                f"missing={len(missing_coverage)}",
                flush=True,
            )
            retry_resolution = semantic_proposal_groups(
                [
                    row
                    for row in results
                    if str(row.get("question_id") or "") in missing_coverage
                ],
                knowledge,
                [
                    row
                    for row in queue
                    if str(row.get("question_id") or "") in missing_coverage
                ],
                min_support=min_support,
                _retry_depth=_retry_depth + 1,
            )
            proposals.extend(retry_resolution["new_points"])
            existing_matches.extend(retry_resolution["existing_matches"])
            deferred.extend(retry_resolution["deferred"])

    deduplicated: dict[tuple[str, str], dict[str, Any]] = {}
    for proposal in proposals:
        key = (proposal["subject"], normalize(proposal["title"]))
        previous = deduplicated.get(key)
        if previous is None:
            deduplicated[key] = proposal
            continue
        previous["question_ids"] = list(
            dict.fromkeys(previous["question_ids"] + proposal["question_ids"])
        )
        previous["chapters"] = sorted(
            set(previous["chapters"]) | set(proposal["chapters"])
        )
        previous["related_existing_ids"] = list(
            dict.fromkeys(
                previous["related_existing_ids"]
                + proposal["related_existing_ids"]
            )
        )
        previous["support_count"] = len(previous["question_ids"])
        previous["confidence"] = max(
            float(previous.get("confidence") or 0),
            float(proposal.get("confidence") or 0),
        )
    return {
        "new_points": sorted(
            deduplicated.values(),
            key=lambda row: row["support_count"],
            reverse=True,
        ),
        "existing_matches": existing_matches,
        "deferred": deferred,
    }


def apply_semantic_gap_resolution(
    resolution: dict[str, list[dict[str, Any]]],
    questions: list[dict[str, Any]],
    knowledge: list[dict[str, Any]],
) -> dict[str, int]:
    if not KNOWLEDGE_EXPANSION_BACKUP.exists():
        shutil.copy2(KNOWLEDGE_PATH, KNOWLEDGE_EXPANSION_BACKUP)
    question_by_id = {str(row.get("id") or ""): row for row in questions}
    knowledge_by_id = {str(row.get("id") or ""): row for row in knowledge}
    chapter_meta: dict[tuple[str, str], dict[str, Any]] = {}
    for point in knowledge:
        chapter_meta[
            (str(point.get("subject") or ""), str(point.get("chapter_title") or ""))
        ] = point
    counts: Counter[str] = Counter()

    for match in resolution.get("existing_matches", []):
        ids = [
            point_id
            for point_id in match.get("knowledge_point_ids") or []
            if point_id in knowledge_by_id
        ]
        if not ids:
            continue
        for question_id in match.get("question_ids") or []:
            question = question_by_id.get(str(question_id))
            if not question:
                continue
            question["knowledge_point_ids"] = ids
            question["knowledge_points"] = [
                knowledge_by_id[point_id]["title"] for point_id in ids
            ]
            question["knowledge_mapping_status"] = "glm_semantic_existing"
            question["knowledge_mapping_confidence"] = match.get("confidence")
            question["knowledge_mapping_evidence"] = match.get("reason")
            counts["remapped_existing"] += 1

    subject_codes = {
        "数据结构": "ds",
        "计算机组成原理": "co",
        "操作系统": "os",
        "计算机网络": "cn",
    }
    for proposal in resolution.get("new_points", []):
        subject = str(proposal.get("subject") or "")
        support_ids = [str(item) for item in proposal.get("question_ids") or []]
        support_questions = [
            question_by_id[item] for item in support_ids if item in question_by_id
        ]
        if not support_questions:
            continue
        primary_chapter = Counter(
            str(question.get("chapter") or "") for question in support_questions
        ).most_common(1)[0][0]
        meta = chapter_meta.get((subject, primary_chapter), {})
        if not meta:
            chapter_match = re.search(r"第\s*(\d+)\s*章", primary_chapter)
            if chapter_match:
                chapter_order = int(chapter_match.group(1))
                meta = next(
                    (
                        point
                        for point in knowledge
                        if point.get("subject") == subject
                        and int(point.get("chapter_order") or 0) == chapter_order
                    ),
                    {},
                )
        title = str(proposal.get("title") or "").strip()
        digest = hashlib.sha1(
            f"{subject}|{normalize(title)}".encode("utf-8")
        ).hexdigest()[:10]
        point_id = f"kp_{subject_codes.get(subject, 'new')}_glm_{digest}"
        suffix = 2
        base_id = point_id
        while point_id in knowledge_by_id:
            point_id = f"{base_id}_{suffix}"
            suffix += 1
        point = {
            "id": point_id,
            "title": title,
            "content": str(proposal.get("description") or "").strip(),
            "subject": subject,
            "chapter_id": meta.get("chapter_id") or f"{subject_codes.get(subject, 'new')}_glm",
            "chapter_title": primary_chapter,
            "chapter_order": meta.get("chapter_order") or 999,
            "knowledge_points": [title],
            "score_points": [],
            "difficulty": "中等",
            "tags": [title],
            "importance": "一般",
            "source": f"{get_settings().glm_model}_semantic_gap",
            "prerequisite_ids": [],
            "related_point_ids": proposal.get("related_existing_ids") or [],
            "cross_subject_point_ids": [],
            "exam_count": len(support_ids),
            "support_question_ids": support_ids,
            "applicable_chapters": proposal.get("chapters") or [primary_chapter],
            "creation_confidence": proposal.get("confidence"),
            "creation_reason": proposal.get("reason"),
        }
        knowledge.append(point)
        knowledge_by_id[point_id] = point
        for question in support_questions:
            question["knowledge_point_ids"] = [point_id]
            question["knowledge_points"] = [title]
            question["knowledge_mapping_status"] = "glm_created_new_point"
            question["knowledge_mapping_confidence"] = proposal.get("confidence")
            question["knowledge_mapping_evidence"] = proposal.get("reason")
            counts["mapped_to_new"] += 1
        counts["new_points_created"] += 1

    write_jsonl(KNOWLEDGE_PATH, knowledge)
    write_jsonl(QUESTION_PATH, questions)
    counts["deferred"] = sum(
        len(item.get("question_ids") or [])
        for item in resolution.get("deferred", [])
    )
    return dict(counts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="调用当前配置模型执行分类")
    parser.add_argument("--apply", action="store_true", help="写回通过严格校验的映射")
    parser.add_argument(
        "--stage",
        action="store_true",
        help="将低置信旧映射降级为待复核，不再用于个性化",
    )
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--new-point-min-support", type=int, default=NEW_POINT_MIN_SUPPORT)
    args = parser.parse_args()

    questions = load_jsonl(QUESTION_PATH)
    knowledge = load_jsonl(KNOWLEDGE_PATH)
    queue = build_review_queue(questions, knowledge)
    write_jsonl(QUEUE_PATH, queue)
    print(f"review_queue={len(queue)} path={QUEUE_PATH}")
    if args.stage:
        print(f"staged={stage_review_queue(questions, queue)}")

    if not args.run:
        print("dry-run: 未调用模型")
        return

    results = classify_queue(
        queue,
        max(1, min(20, args.batch_size)),
        max(1, min(4, args.workers)),
    )
    if args.apply:
        print("applied", apply_verified_mappings(questions, knowledge, results))
    else:
        print("not applied: add --apply after reviewing result files")

    resolution = semantic_proposal_groups(
        results,
        knowledge,
        queue,
        max(1, args.new_point_min_support),
    )
    PROPOSAL_PATH.write_text(
        json.dumps(resolution, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.apply:
        print(
            "semantic_applied",
            apply_semantic_gap_resolution(
                resolution,
                questions,
                knowledge,
            ),
        )
    print(
        f"results={len(results)} "
        f"new_points={len(resolution['new_points'])} "
        f"existing_matches={len(resolution['existing_matches'])} "
        f"deferred={len(resolution['deferred'])}"
    )


if __name__ == "__main__":
    main()
