from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaoyan_ai.agents.base import LLMClient
from kaoyan_ai.config import get_settings
from kaoyan_ai.question_quality import question_is_well_formed


ROOT = Path(__file__).resolve().parents[1]
QUESTION_PATH = ROOT / "data" / "question_bank.jsonl"
CHECKPOINT_PATH = ROOT / "tmp" / "question_answer_alignment_checkpoint.jsonl"
MANIFEST_PATH = ROOT / "data" / "question_answer_alignment_manifest.json"
MODEL_NAME = "qwen3.8-max"
VALID_ANSWERS = {"A", "B", "C", "D"}
SYSTEM_PROMPT = """你是严谨的计算机考研408题库审校专家。
你要逐题独立求解，检查当前答案是否正确、当前解析是否真正对应本题。

判定标准：
1. 必须依据题干和给出的选项独立求解，不能因为“当前答案”而迎合。
2. aligned 表示解析直接解释本题、支持正确选项，并能排除主要干扰项。
3. misaligned 表示解析讲的是别的题、与题干无关、支持了另一个选项，或明显答非所问。
4. insufficient 表示解析相关但过短、关键推导缺失；它不是错配。
5. 若题干或选项残缺到无法可靠作答，answer_status 填 uncertain。
6. corrected_explanation 必须针对本题，简洁严谨，明确说明正确选项为何成立。
7. 解析先给出规范、可靠的标准方法；若本题存在更直观的判断、口诀、排除法、
   速算或其他简便方法，再增加“简便方法：...”说明。没有可靠简便方法时不要硬凑。
8. 只输出 JSON 数组，不要 Markdown，不要额外文字。

每项格式：
{"id":"题号","solved_answer":"A|B|C|D","answer_status":"correct|incorrect|uncertain",
"explanation_status":"aligned|misaligned|insufficient",
"corrected_explanation":"仅当答案错误或解析错配时填写，否则为空字符串",
"confidence":0.0}
"""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def atomic_write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".alignment.tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def normalize_answer(value: object) -> str:
    match = re.search(r"[A-D]", str(value or "").strip().upper())
    return match.group(0) if match else ""


def build_user_prompt(batch: list[dict[str, Any]]) -> str:
    payload = []
    for question in batch:
        payload.append(
            {
                "id": question.get("id"),
                "subject": question.get("subject"),
                "stem": question.get("content") or question.get("title"),
                "options": question.get("options") or [],
                "current_answer": normalize_answer(question.get("answer")),
                "current_explanation": question.get("explanation")
                or question.get("analysis")
                or "",
            }
        )
    return (
        "请按输入顺序审校以下题目，每道题必须返回一项。输入：\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def parse_json_array(text: str) -> list[dict[str, Any]]:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", cleaned)
    candidates = [fenced.group(1)] if fenced else []
    first = cleaned.find("[")
    last = cleaned.rfind("]")
    if first >= 0 and last > first:
        candidates.append(cleaned[first : last + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return value
    raise ValueError("模型响应中没有可解析的 JSON 数组")


def validate_result(
    raw: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    question_id = str(expected.get("id") or "")
    if str(raw.get("id") or "") != question_id:
        raise ValueError(f"返回题号不匹配：期望 {question_id}")
    answer = normalize_answer(raw.get("solved_answer"))
    answer_status = str(raw.get("answer_status") or "").strip().lower()
    explanation_status = str(raw.get("explanation_status") or "").strip().lower()
    if answer not in VALID_ANSWERS:
        raise ValueError(f"{question_id} 缺少有效答案")
    if answer_status not in {"correct", "incorrect", "uncertain"}:
        raise ValueError(f"{question_id} 答案状态无效")
    if explanation_status not in {"aligned", "misaligned", "insufficient"}:
        raise ValueError(f"{question_id} 解析状态无效")
    confidence = max(0.0, min(1.0, float(raw.get("confidence") or 0)))
    current_answer = normalize_answer(expected.get("answer"))
    if answer_status != "uncertain":
        answer_status = "correct" if answer == current_answer else "incorrect"
    explanation = str(raw.get("corrected_explanation") or "").strip()
    if (
        answer_status == "incorrect" or explanation_status == "misaligned"
    ) and not explanation:
        raise ValueError(f"{question_id} 需要修复但没有返回新解析")
    return {
        "id": question_id,
        "solved_answer": answer,
        "answer_status": answer_status,
        "explanation_status": explanation_status,
        "corrected_explanation": explanation,
        "confidence": confidence,
        "model": MODEL_NAME,
    }


def audit_batch(
    batch_index: int,
    batch: list[dict[str, Any]],
    model_config: tuple[str, str, str],
    retries: int,
) -> tuple[int, list[dict[str, Any]]]:
    model, api_key, base_url = model_config
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = LLMClient().generate(
                SYSTEM_PROMPT,
                build_user_prompt(batch),
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
            if "大模型服务暂时不可用" in response:
                raise RuntimeError(response.splitlines()[0])
            items = parse_json_array(response)
            by_id = {str(item.get("id") or ""): item for item in items}
            if len(by_id) != len(batch):
                raise ValueError(
                    f"返回 {len(by_id)} 项，期望 {len(batch)} 项"
                )
            validated = [
                validate_result(by_id[str(question.get("id") or "")], question)
                for question in batch
            ]
            return batch_index, validated
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(attempt * 1.5)
    raise RuntimeError(f"批次 {batch_index} 审校失败：{last_error}")


def load_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    results: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        results[str(item["id"])] = item
    return results


def append_checkpoint(
    path: Path,
    items: list[dict[str, Any]],
    lock: threading.Lock,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items)
    with lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text)


def audit_questions(
    questions: list[dict[str, Any]],
    checkpoint_path: Path,
    batch_size: int,
    workers: int,
    retries: int,
) -> dict[str, dict[str, Any]]:
    settings = get_settings()
    api_key = settings.glm_api_key
    base_url = settings.glm_base_url
    if not api_key:
        raise RuntimeError("GLM_API_KEY 未配置，无法运行题库审校")
    existing = load_checkpoint(checkpoint_path)
    pending = [
        question
        for question in questions
        if question_is_well_formed(question)
        and str(question.get("id") or "") not in existing
    ]
    batches = [
        pending[index : index + batch_size]
        for index in range(0, len(pending), batch_size)
    ]
    print(
        f"题库 {len(questions)} 题；结构有效 "
        f"{sum(question_is_well_formed(q) for q in questions)} 题；"
        f"已审校 {len(existing)} 题；待审校 {len(pending)} 题。"
    )
    if not batches:
        return existing

    lock = threading.Lock()
    completed = 0
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                audit_batch,
                batch_index,
                batch,
                (MODEL_NAME, api_key, base_url),
                retries,
            ): batch_index
            for batch_index, batch in enumerate(batches, 1)
        }
        for future in as_completed(futures):
            try:
                batch_index, items = future.result()
            except Exception as exc:
                failures.append(str(exc))
                print(f"[批次失败] {exc}", flush=True)
                continue
            append_checkpoint(checkpoint_path, items, lock)
            existing.update({item["id"]: item for item in items})
            completed += len(items)
            print(
                f"[{completed}/{len(pending)}] 批次 {batch_index}/{len(batches)} 完成",
                flush=True,
            )
    if failures:
        raise RuntimeError(
            f"{len(failures)} 个批次失败；成功结果已保存，可用同一检查点续跑。"
        )
    return existing


def apply_repairs(
    questions: list[dict[str, Any]],
    results: dict[str, dict[str, Any]],
    confidence_threshold: float,
) -> dict[str, Any]:
    changes = []
    status_counts: Counter[str] = Counter()
    for question in questions:
        question_id = str(question.get("id") or "")
        result = results.get(question_id)
        if not result:
            continue
        status_counts[f"answer_{result['answer_status']}"] += 1
        status_counts[f"explanation_{result['explanation_status']}"] += 1
        confidence = float(result.get("confidence") or 0)
        if confidence < confidence_threshold:
            continue
        fix_answer = result["answer_status"] == "incorrect"
        fix_explanation = result["explanation_status"] == "misaligned"
        if not (fix_answer or fix_explanation):
            continue
        old_answer = normalize_answer(question.get("answer"))
        old_explanation = str(question.get("explanation") or "")
        if fix_answer:
            question["answer"] = result["solved_answer"]
        question["explanation"] = result["corrected_explanation"]
        changes.append(
            {
                "id": question_id,
                "subject": question.get("subject"),
                "content": question.get("content") or question.get("title"),
                "old_answer": old_answer,
                "new_answer": normalize_answer(question.get("answer")),
                "answer_changed": fix_answer,
                "explanation_replaced": True,
                "old_explanation": old_explanation,
                "new_explanation": question["explanation"],
                "reason": {
                    "answer_status": result["answer_status"],
                    "explanation_status": result["explanation_status"],
                },
                "confidence": confidence,
            }
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = QUESTION_PATH.with_name(
        f"question_bank.before_answer_alignment_{timestamp}.jsonl"
    )
    shutil.copy2(QUESTION_PATH, backup)
    atomic_write_jsonl(QUESTION_PATH, questions)
    manifest = {
        "models": dict(
            sorted(Counter(item.get("model") or "unknown" for item in results.values()).items())
        ),
        "confidence_threshold": confidence_threshold,
        "question_count": len(questions),
        "audited_count": len(results),
        "status_counts": dict(sorted(status_counts.items())),
        "repaired_count": len(changes),
        "answer_changes": sum(item["answer_changed"] for item in changes),
        "explanation_replacements": len(changes),
        "backup": str(backup.relative_to(ROOT)).replace("\\", "/"),
        "changes": changes,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="用指定 Qwen 模型审校并修复题目、答案和解析的对应关系。"
    )
    parser.add_argument("--input", type=Path, default=QUESTION_PATH)
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT_PATH)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--confidence", type=float, default=0.88)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="审校完成后回写达到置信度门槛的修复；默认只生成审校检查点。",
    )
    args = parser.parse_args()

    questions = load_jsonl(args.input)
    results = audit_questions(
        questions,
        args.checkpoint,
        max(1, args.batch_size),
        max(1, args.workers),
        max(1, args.retries),
    )
    if args.apply:
        manifest = apply_repairs(questions, results, args.confidence)
        print(
            f"已修复 {manifest['repaired_count']} 题："
            f"答案改动 {manifest['answer_changes']}，"
            f"解析替换 {manifest['explanation_replacements']}。"
        )
        print(f"清单：{MANIFEST_PATH}")
        print(f"备份：{manifest['backup']}")
    else:
        print(f"审校结果已保存：{args.checkpoint}")


if __name__ == "__main__":
    main()
