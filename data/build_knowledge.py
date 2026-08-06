"""根据 4 大科目课程数据生成 data/knowledge_points.jsonl。

数据结构（每行一条 JSON）：
{
  "id": "kp_<subject>_<chapter>_<n>",
  "title": "...",
  "content": "...",
  "subject": "...",
  "chapter_id": "...",
  "chapter_title": "...",
  "chapter_order": N,
  "knowledge_points": [...],
  "score_points": [...],
  "difficulty": "基础|中等|较难",
  "tags": [...],
  "source": "curriculum"
}

执行：python -m data.build_knowledge
"""

from __future__ import annotations

import json
from pathlib import Path

from data.curriculum_co import CHAPTERS as CO_CH
from data.curriculum_cn import CHAPTERS as CN_CH
from data.curriculum_ds import CHAPTERS as DS_CH
from data.curriculum_os import CHAPTERS as OS_CH


SUBJECTS = [
    ("数据结构", DS_CH),
    ("计算机组成原理", CO_CH),
    ("操作系统", OS_CH),
    ("计算机网络", CN_CH),
]


def build_records() -> list[dict]:
    records: list[dict] = []
    for subject, chapters in SUBJECTS:
        subj_prefix = {
            "数据结构": "ds",
            "计算机组成原理": "co",
            "操作系统": "os",
            "计算机网络": "cn",
        }[subject]
        for chapter in chapters:
            chapter_id = chapter["chapter_id"]
            for idx, point in enumerate(chapter["points"], start=1):
                record_id = f"kp_{subj_prefix}_{chapter_id}_{idx:02d}"
                records.append(
                    {
                        "id": record_id,
                        "title": point["title"],
                        "content": point["content"],
                        "subject": subject,
                        "chapter_id": chapter_id,
                        "chapter_title": chapter["chapter_title"],
                        "chapter_order": chapter["chapter_order"],
                        "knowledge_points": [point["title"]] + point.get("tags", []),
                        "score_points": point.get("score_points", []),
                        "difficulty": point.get("difficulty", "中等"),
                        "tags": point.get("tags", []),
                        "importance": point.get("importance", "一般"),
                        "exam_questions": point.get("exam_questions", []),
                        "exam_count": point.get("exam_count", 0),
                        "detailed_explanation": point.get("detailed_explanation", ""),
                        "source": "curriculum",
                    }
                )
    return records


def main() -> None:
    """生成 JSONL 知识库文件。"""

    records = build_records()
    output = Path("data/knowledge_points.jsonl")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(
        {
            "total": len(records),
            "subjects": [s for s, _ in SUBJECTS],
            "output": str(output),
        },
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
