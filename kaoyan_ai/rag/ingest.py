from __future__ import annotations

import argparse
import json
from pathlib import Path

from kaoyan_ai.utils.jsonl import append_jsonl


def ingest_markdown(source: Path, output: Path, subject: str) -> int:
    """把 Markdown 文件切分为知识片段，并追加写入 JSONL。"""

    content = source.read_text(encoding="utf-8")
    chunks = [chunk.strip() for chunk in content.split("\n## ") if chunk.strip()]
    count = 0
    for index, chunk in enumerate(chunks, start=1):
        title = chunk.splitlines()[0].replace("#", "").strip()
        append_jsonl(
            output,
            {
                "id": f"{source.stem}-{index}",
                "title": title,
                "content": chunk,
                "subject": subject,
                "knowledge_points": [title],
                "difficulty": "中等",
                "source": str(source),
                "score_points": [],
            },
        )
        count += 1
    return count


def main() -> None:
    """导入 Markdown 知识笔记的命令行入口。"""

    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/knowledge_points.jsonl"))
    parser.add_argument("--subject", required=True)
    args = parser.parse_args()
    count = ingest_markdown(args.source, args.output, args.subject)
    print(json.dumps({"ingested": count}, ensure_ascii=False))


if __name__ == "__main__":
    main()
