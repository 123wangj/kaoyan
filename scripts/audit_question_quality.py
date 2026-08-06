from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from kaoyan_ai.question_quality import question_quality_issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit question-bank structural quality.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/question_bank.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/question_quality_manifest.json"),
    )
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rejected = []
    for question in rows:
        issues = question_quality_issues(question)
        if issues:
            rejected.append(
                {
                    "id": question.get("id"),
                    "subject": question.get("subject"),
                    "chapter": question.get("chapter"),
                    "question_number": question.get("question_number"),
                    "issues": issues,
                    "content": question.get("content") or question.get("title"),
                }
            )

    manifest = {
        "source": str(args.input).replace("\\", "/"),
        "total_questions": len(rows),
        "visible_after_quality_filter": len(rows) - len(rejected),
        "hidden_questions": len(rejected),
        "issue_counts": dict(
            sorted(Counter(issue for row in rejected for issue in row["issues"]).items())
        ),
        "hidden_by_subject": dict(
            sorted(Counter(str(row["subject"] or "未分类") for row in rejected).items())
        ),
        "questions": rejected,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Audited {len(rows)} questions: "
        f"{len(rejected)} hidden, {len(rows) - len(rejected)} retained."
    )


if __name__ == "__main__":
    main()
