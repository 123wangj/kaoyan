from __future__ import annotations

import json
import re
import shutil
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaoyan_ai.agents.base import LLMClient
from kaoyan_ai.config import get_settings
from kaoyan_ai.question_quality import question_is_well_formed
from scripts.repair_question_answer_alignment import (
    MODEL_NAME,
    atomic_write_jsonl,
    load_jsonl,
    normalize_answer,
    parse_json_array,
)


ROOT = Path(__file__).resolve().parents[1]
QUESTION_PATH = ROOT / "data" / "question_bank.jsonl"
CHECKPOINT_PATH = ROOT / "tmp" / "duplicate_explanation_refinement.jsonl"
MANIFEST_PATH = ROOT / "data" / "question_explanation_refinement_manifest.json"
SYSTEM_PROMPT = """你是严谨的计算机考研408题库审校专家。
请对每道题独立求解，重新撰写专属于该题的解析，不得复用泛化模板。

要求：
1. answer 只能是 A、B、C、D。
2. explanation 先给规范可靠的标准方法，直接结合本题题干和选项说明。
3. 若存在可靠的排除法、口诀、速算、直观判断等，再在末尾加入
   “简便方法：...”。并非每题都必须有，不能硬凑。
4. 题干或选项不足以可靠作答时 confidence 必须低于 0.88。
5. 只输出 JSON 数组，不要 Markdown和额外文字。

格式：
{"id":"题号","answer":"A|B|C|D","explanation":"本题专属解析","confidence":0.0}
"""


def duplicate_candidates(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for question in questions:
        if not question_is_well_formed(question):
            continue
        explanation = re.sub(
            r"\s+", "", str(question.get("explanation") or "")
        )
        if explanation:
            groups[explanation].append(question)
    ids = {
        str(question.get("id") or "")
        for group in groups.values()
        if len(group) > 1
        for question in group
    }
    return [question for question in questions if str(question.get("id") or "") in ids]


def prompt_for(batch: list[dict[str, Any]]) -> str:
    payload = [
        {
            "id": question.get("id"),
            "subject": question.get("subject"),
            "stem": question.get("content") or question.get("title"),
            "options": question.get("options") or [],
        }
        for question in batch
    ]
    return "逐题独立求解并重写解析：\n" + json.dumps(payload, ensure_ascii=False)


def run_batch(
    index: int,
    batch: list[dict[str, Any]],
    model: str,
    api_key: str,
    base_url: str,
) -> tuple[int, list[dict[str, Any]]]:
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            response = LLMClient().generate(
                SYSTEM_PROMPT,
                prompt_for(batch),
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
            if "大模型服务暂时不可用" in response:
                raise RuntimeError(response.splitlines()[0])
            raw_items = parse_json_array(response)
            by_id = {str(item.get("id") or ""): item for item in raw_items}
            results = []
            for question in batch:
                question_id = str(question.get("id") or "")
                item = by_id.get(question_id)
                if not item:
                    raise ValueError(f"缺少题目 {question_id}")
                answer = normalize_answer(item.get("answer"))
                explanation = str(item.get("explanation") or "").strip()
                confidence = max(
                    0.0, min(1.0, float(item.get("confidence") or 0))
                )
                if not answer or not explanation:
                    raise ValueError(f"{question_id} 返回内容不完整")
                results.append(
                    {
                        "id": question_id,
                        "answer": answer,
                        "explanation": explanation,
                        "confidence": confidence,
                        "model": MODEL_NAME,
                    }
                )
            return index, results
        except Exception as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(attempt * 1.5)
    raise RuntimeError(f"批次 {index} 失败：{last_error}")


def main() -> None:
    questions = load_jsonl(QUESTION_PATH)
    candidates = duplicate_candidates(questions)
    completed = {
        str(item["id"]): item
        for item in load_jsonl(CHECKPOINT_PATH)
    } if CHECKPOINT_PATH.exists() else {}
    pending = [
        question
        for question in candidates
        if str(question.get("id") or "") not in completed
    ]
    batches = [pending[i : i + 8] for i in range(0, len(pending), 8)]
    settings = get_settings()
    if not settings.glm_api_key:
        raise RuntimeError("GLM_API_KEY 未配置")
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    failures = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(
                run_batch,
                index,
                batch,
                MODEL_NAME,
                settings.glm_api_key,
                settings.glm_base_url,
            ): index
            for index, batch in enumerate(batches, 1)
        }
        for future in as_completed(futures):
            try:
                index, items = future.result()
            except Exception as exc:
                failures.append(str(exc))
                print(f"[批次失败] {exc}", flush=True)
                continue
            with lock:
                with CHECKPOINT_PATH.open("a", encoding="utf-8") as handle:
                    for item in items:
                        handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            completed.update({item["id"]: item for item in items})
            print(f"批次 {index}/{len(batches)} 完成", flush=True)
    if failures:
        raise RuntimeError("存在失败批次；结果已保存，请使用同一检查点续跑")

    changes = []
    for question in questions:
        item = completed.get(str(question.get("id") or ""))
        if not item or float(item.get("confidence") or 0) < 0.88:
            continue
        old_answer = normalize_answer(question.get("answer"))
        old_explanation = str(question.get("explanation") or "")
        question["answer"] = item["answer"]
        question["explanation"] = item["explanation"]
        changes.append(
            {
                "id": question.get("id"),
                "subject": question.get("subject"),
                "old_answer": old_answer,
                "new_answer": item["answer"],
                "answer_changed": old_answer != item["answer"],
                "old_explanation": old_explanation,
                "new_explanation": item["explanation"],
                "confidence": item["confidence"],
                "has_simple_method": "简便方法" in item["explanation"],
            }
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = QUESTION_PATH.with_name(
        f"question_bank.before_explanation_refinement_{timestamp}.jsonl"
    )
    shutil.copy2(QUESTION_PATH, backup)
    atomic_write_jsonl(QUESTION_PATH, questions)
    manifest = {
        "model": MODEL_NAME,
        "candidate_count": len(candidates),
        "refined_count": len(changes),
        "answer_changes": sum(item["answer_changed"] for item in changes),
        "simple_method_additions": sum(item["has_simple_method"] for item in changes),
        "backup": str(backup.relative_to(ROOT)).replace("\\", "/"),
        "changes": changes,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in manifest.items() if key != "changes"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
