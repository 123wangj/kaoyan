from __future__ import annotations

import base64
import json
import re
import shutil
import sys
import threading
import time
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
)


ROOT = Path(__file__).resolve().parents[1]
QUESTION_PATH = ROOT / "data" / "question_bank.jsonl"
FIRST_PASS_PATH = ROOT / "tmp" / "qwen37_max_answer_alignment.jsonl"
CHECKPOINT_PATH = ROOT / "tmp" / "unresolved_alignment_review.jsonl"
IMAGE_OVERRIDE_PATH = ROOT / "data" / "unresolved_image_review_overrides.jsonl"
MANIFEST_PATH = ROOT / "data" / "unresolved_alignment_review_manifest.json"
SYSTEM_PROMPT = """你是计算机考研408题库终审专家。请独立复核单道选择题。

先判断仅凭当前题干、选项和附图能否可靠作答：
- 缺少公式、代码、表格、图、前置数据，或者选项内容残缺时，recoverable=false。
- 不允许靠猜测或声称记得某道原题来补全缺失信息。
- recoverable=true 时，独立求解并给出正确选项和本题专属解析。
- 解析先写规范方法；确有可靠技巧时再写“简便方法：...”，不强行添加。
- confidence 只有在题目完整且答案确定时才能达到0.90以上。

只输出一个JSON对象：
{"id":"题号","recoverable":true,"answer":"A|B|C|D",
"explanation":"解析","confidence":0.0,"damage_reason":"不可恢复时说明缺什么"}
"""


def unresolved_ids(
    questions: list[dict[str, Any]],
    first_pass: dict[str, dict[str, Any]],
) -> set[str]:
    result = set()
    for question in questions:
        if not question_is_well_formed(question):
            continue
        question_id = str(question.get("id") or "")
        audit = first_pass.get(question_id)
        if not audit:
            continue
        confidence = float(audit.get("confidence") or 0)
        if (
            audit.get("answer_status") == "uncertain"
            or (
                audit.get("explanation_status") == "misaligned"
                and confidence < 0.88
            )
            or (
                audit.get("answer_status") == "incorrect"
                and confidence < 0.88
            )
        ):
            result.add(question_id)
    return result


def extract_object(text: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    candidates = [fenced.group(1)] if fenced else []
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("模型响应中没有有效JSON对象")


def image_payload(question: dict[str, Any]) -> str | None:
    image_url = str(question.get("image_url") or "")
    if not image_url.startswith("/static/"):
        return None
    path = ROOT / image_url.lstrip("/")
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode("ascii")


def review_one(
    question: dict[str, Any],
    model: str,
    api_key: str,
    base_url: str,
) -> dict[str, Any]:
    question_id = str(question.get("id") or "")
    prompt = json.dumps(
        {
            "id": question_id,
            "subject": question.get("subject"),
            "stem": question.get("content") or question.get("title"),
            "options": question.get("options") or [],
        },
        ensure_ascii=False,
    )
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            response = LLMClient().generate(
                SYSTEM_PROMPT,
                prompt,
                image_base64=image_payload(question),
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
            if "大模型服务暂时不可用" in response:
                raise RuntimeError(response.splitlines()[0])
            raw = extract_object(response)
            if str(raw.get("id") or "") != question_id:
                raise ValueError("返回题号不匹配")
            recoverable = bool(raw.get("recoverable"))
            answer = normalize_answer(raw.get("answer"))
            explanation = str(raw.get("explanation") or "").strip()
            confidence = max(0.0, min(1.0, float(raw.get("confidence") or 0)))
            damage_reason = str(raw.get("damage_reason") or "").strip()
            if recoverable and (not answer or not explanation):
                raise ValueError("可恢复题缺少答案或解析")
            if not recoverable and not damage_reason:
                raise ValueError("不可恢复题缺少损坏原因")
            return {
                "id": question_id,
                "recoverable": recoverable,
                "answer": answer,
                "explanation": explanation,
                "confidence": confidence,
                "damage_reason": damage_reason,
                "model": MODEL_NAME,
                "used_image": bool(image_payload(question)),
            }
        except Exception as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(attempt * 1.5)
    raise RuntimeError(f"{question_id} 复核失败：{last_error}")


def main() -> None:
    questions = load_jsonl(QUESTION_PATH)
    first_pass = {
        str(item["id"]): item for item in load_jsonl(FIRST_PASS_PATH)
    }
    target_ids = unresolved_ids(questions, first_pass)
    completed = {
        str(item["id"]): item for item in load_jsonl(CHECKPOINT_PATH)
    } if CHECKPOINT_PATH.exists() else {}
    if IMAGE_OVERRIDE_PATH.exists():
        completed.update(
            {
                str(item["id"]): item
                for item in load_jsonl(IMAGE_OVERRIDE_PATH)
            }
        )
    pending = [
        question
        for question in questions
        if str(question.get("id") or "") in target_ids
        and str(question.get("id") or "") not in completed
    ]
    settings = get_settings()
    if not settings.glm_api_key:
        raise RuntimeError("GLM_API_KEY 未配置")
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    failures = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(
                review_one,
                question,
                MODEL_NAME,
                settings.glm_api_key,
                settings.glm_base_url,
            ): str(question.get("id") or "")
            for question in pending
        }
        for future in as_completed(futures):
            try:
                item = future.result()
            except Exception as exc:
                failures.append(str(exc))
                print(f"[失败] {exc}", flush=True)
                continue
            with lock:
                with CHECKPOINT_PATH.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            completed[item["id"]] = item
            print(f"[{len(completed)}/{len(target_ids)}] {item['id']}", flush=True)
    if failures:
        raise RuntimeError("存在失败题目；成功结果已保存，可续跑")

    changes = []
    hidden = []
    for question in questions:
        question_id = str(question.get("id") or "")
        item = completed.get(question_id)
        if not item:
            continue
        if item["recoverable"] and float(item["confidence"]) >= 0.90:
            old_answer = normalize_answer(question.get("answer"))
            question["answer"] = item["answer"]
            question["explanation"] = item["explanation"]
            question.pop("quality_status", None)
            question.pop("quality_reason", None)
            changes.append(
                {
                    "id": question_id,
                    "old_answer": old_answer,
                    "new_answer": item["answer"],
                    "answer_changed": old_answer != item["answer"],
                    "confidence": item["confidence"],
                    "used_image": item["used_image"],
                    "explanation": item["explanation"],
                }
            )
        else:
            question["quality_status"] = "unrecoverable_alignment"
            question["quality_reason"] = (
                item["damage_reason"]
                or f"二次复核置信度仅 {item['confidence']:.2f}"
            )
            hidden.append(
                {
                    "id": question_id,
                    "reason": question["quality_reason"],
                    "confidence": item["confidence"],
                    "used_image": item["used_image"],
                }
            )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = QUESTION_PATH.with_name(
        f"question_bank.before_unresolved_review_{timestamp}.jsonl"
    )
    shutil.copy2(QUESTION_PATH, backup)
    atomic_write_jsonl(QUESTION_PATH, questions)
    manifest = {
        "model": MODEL_NAME,
        "target_count": len(target_ids),
        "repaired_count": len(changes),
        "answer_changes": sum(item["answer_changed"] for item in changes),
        "hidden_count": len(hidden),
        "simple_method_count": sum(
            "简便方法" in item["explanation"] for item in changes
        ),
        "backup": str(backup.relative_to(ROOT)).replace("\\", "/"),
        "repairs": changes,
        "hidden": hidden,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: v for k, v in manifest.items() if k not in {"repairs", "hidden"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
