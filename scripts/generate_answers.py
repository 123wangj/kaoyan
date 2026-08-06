"""
批量生成题库答案和解析

读取所有 JSONL 题库文件，对缺少答案的题目调用大模型生成答案和解析，
并写回 JSONL 文件。

使用方法：
    python scripts/generate_answers.py
    python scripts/generate_answers.py --subject 数据结构
    python scripts/generate_answers.py --file data/question_bank.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kaoyan_ai.agents.base import LLMClient
from kaoyan_ai.utils.jsonl import load_jsonl


def _build_system_prompt() -> str:
    return (
        "你是计算机考研408辅导专家。你负责为408考研题目生成准确的参考答案和详细解析。\n"
        "要求：\n"
        "1. 对于选择题，只输出选项字母（如A、B、C、D）作为答案。\n"
        "2. 解析内容应包括：考点归属、解题思路、关键步骤、踩分点提示。\n"
        "3. 所有解答必须在408考纲范围内（数据结构、计算机组成原理、操作系统、计算机网络）。\n"
        "4. 严格按照以下JSON格式输出，不要输出任何其他内容：\n"
        '{"answer": "答案字母", "explanation": "详细解析内容"}\n'
        "5. 参考《王道考研》系列教材的解析风格，保持严谨、简洁、准确。"
    )


def _build_user_prompt(question: dict) -> str:
    content = question.get("content", "")
    subject = question.get("subject", "")
    options = question.get("options", [])
    qtype = question.get("type", "choice")
    source = question.get("source", "")

    options_text = "\n".join(options) if options else "无选项"

    return f"""
请为下面这道408考研题目生成答案和解析。

来源：{source}
科目：{subject}
题型：{qtype}
题目内容：{content}

选项：
{options_text}

请严格按照JSON格式输出。
"""


def _parse_llm_response(result_text: str) -> tuple[str, str]:
    """从 LLM 返回文本中提取答案和解析。"""

    # 尝试提取 JSON
    json_match = re.search(
        r'\{[^{}]*"answer"[^{}]*"explanation"[^{}]*\}', result_text, re.DOTALL
    )
    if not json_match:
        json_match = re.search(r'\{[^{}]*\}', result_text, re.DOTALL)

    if json_match:
        try:
            result = json.loads(json_match.group(0))
            answer = result.get("answer", "").strip()
            explanation = result.get("explanation", "").strip()
            return answer, explanation
        except json.JSONDecodeError:
            pass

    # 回退：从文本中提取答案
    answer_match = re.search(r'(?:答案|正确选项)[：:]\s*([A-D])', result_text)
    answer = answer_match.group(1) if answer_match else ""

    # 清理文本作为解析
    explanation = result_text.replace("```json", "").replace("```", "").strip()
    if len(explanation) > 1000:
        explanation = explanation[:1000]

    return answer, explanation


def _update_jsonl(filepath: Path, question_id: str, answer: str, explanation: str) -> bool:
    """更新 JSONL 文件中指定题目的答案和解析。"""

    questions = load_jsonl(filepath)
    updated = False

    for q in questions:
        if q.get("id") == question_id:
            q["answer"] = answer
            q["explanation"] = explanation
            updated = True
            break

    if not updated:
        return False

    with filepath.open("w", encoding="utf-8") as f:
        for q in questions:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    return True


def generate_answers(
    filepaths: list[Path] | None = None,
    subject_filter: str | None = None,
    dry_run: bool = False,
    delay: float = 0.5,
) -> dict:
    """批量生成答案和解析。

    Args:
        filepaths: 要处理的 JSONL 文件列表，默认处理 data/ 下的所有题库文件。
        subject_filter: 只处理指定科目。
        dry_run: 只统计不实际生成。
        delay: 每次 LLM 调用间的等待秒数。
    """

    if filepaths is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
        filepaths = sorted(data_dir.glob("question_bank*.jsonl"))

    llm = LLMClient()
    system_prompt = _build_system_prompt()

    stats = {"total": 0, "processed": 0, "skipped": 0, "failed": 0}

    for filepath in filepaths:
        if not filepath.exists():
            print(f"[跳过] 文件不存在: {filepath}")
            continue

        questions = load_jsonl(filepath)
        file_total = 0
        file_processed = 0
        file_skipped = 0
        file_failed = 0

        for i, q in enumerate(questions, 1):
            qid = q.get("id", "")
            if not qid:
                continue

            # 科目筛选
            if subject_filter and q.get("subject") != subject_filter:
                continue

            # 跳过已有答案的题
            if q.get("answer") and q["answer"].strip():
                file_skipped += 1
                stats["skipped"] += 1
                continue

            content = q.get("content", "")
            options = q.get("options", [])
            qtype = q.get("type", "choice")

            if not content:
                continue

            file_total += 1
            stats["total"] += 1

            q_number = q.get("question_number", str(i))
            source = q.get("source", "")
            print(f"\n[{file_total}] {source} 第{q_number}题 | {q.get('subject','')} | {content[:60]}...")

            if dry_run:
                print("  [dry-run] 跳过生成")
                continue

            user_prompt = _build_user_prompt(q)

            try:
                result_text = llm.generate(system_prompt, user_prompt)
                answer, explanation = _parse_llm_response(result_text)

                if not answer:
                    print(f"  [警告] 未能提取到答案，原始响应: {result_text[:200]}")
                    file_failed += 1
                    stats["failed"] += 1
                    continue

                print(f"  [答案] {answer}")
                print(f"  [解析] {explanation[:120]}...")

                if _update_jsonl(filepath, qid, answer, explanation):
                    file_processed += 1
                    stats["processed"] += 1
                    print(f"  [保存成功]")
                else:
                    file_failed += 1
                    stats["failed"] += 1
                    print(f"  [保存失败]")

                time.sleep(delay)

            except Exception as e:
                print(f"  [错误] {e}")
                file_failed += 1
                stats["failed"] += 1

        print(f"\n--- 文件 {filepath.name} 处理完成 ---")
        print(f"  处理: {file_processed} | 跳过(已有答案): {file_skipped} | 失败: {file_failed}")

    return stats


def main():
    parser = argparse.ArgumentParser(description="批量生成408考研题库答案和解析")
    parser.add_argument(
        "--subject",
        type=str,
        default=None,
        choices=["数据结构", "计算机组成原理", "操作系统", "计算机网络"],
        help="只处理指定科目的题目",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="指定单个 JSONL 文件，默认处理 data/ 下所有 question_bank*.jsonl",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只统计不实际生成答案",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="每次 LLM 调用间的等待秒数（默认0.5）",
    )
    args = parser.parse_args()

    if args.file:
        filepaths = [Path(args.file)]
    else:
        filepaths = None  # 使用默认值

    print("=" * 60)
    print("  408考研题库答案批量生成工具")
    print("=" * 60)
    if args.subject:
        print(f"  科目筛选: {args.subject}")
    if args.dry_run:
        print(f"  模式: dry-run（仅统计）")
    print()

    start_time = time.time()
    stats = generate_answers(
        filepaths=filepaths,
        subject_filter=args.subject,
        dry_run=args.dry_run,
        delay=args.delay,
    )
    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print(f"  全部完成！耗时 {elapsed:.1f} 秒")
    print(f"  总计: {stats['total']} | 生成: {stats['processed']} | 跳过(已有): {stats['skipped']} | 失败: {stats['failed']}")
    print("=" * 60)


if __name__ == "__main__":
    main()