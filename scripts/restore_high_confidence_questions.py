from __future__ import annotations

import argparse
import copy
import difflib
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from kaoyan_ai.question_quality import question_quality_issues


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_BANK = ROOT / "data" / "question_bank.jsonl"
REFERENCE_BANK = ROOT / "data" / "question_bank_mcq.jsonl"
BACKUP_BANK = ROOT / "data" / "question_bank.before_quality_restore.jsonl"
MANIFEST_PATH = ROOT / "data" / "question_restore_manifest.json"
MIN_SCORE = 0.82
MIN_MARGIN = 0.08


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def normalize(value: object) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[\u3400-\u4dbf\ue000-\uf8ff\ufffd]", "", text)
    return re.sub(r"\W+", "", text)


def candidate_key(question: dict[str, Any]) -> tuple[object, object, str]:
    return (
        question.get("subject"),
        question.get("source"),
        str(question.get("question_number")),
    )


def similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    return difflib.SequenceMatcher(
        None,
        normalize(left.get("content") or left.get("title")),
        normalize(right.get("content") or right.get("title")),
    ).ratio()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".restore.tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restore only high-confidence malformed questions."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    active = load_jsonl(ACTIVE_BANK)
    references = load_jsonl(REFERENCE_BANK)
    reference_index: dict[tuple[object, object, str], list[dict[str, Any]]] = defaultdict(list)
    for question in references:
        if not question_quality_issues(question):
            reference_index[candidate_key(question)].append(question)

    restored = []
    skipped_after_validation = []
    for line_number, question in enumerate(active, start=1):
        before_issues = question_quality_issues(question)
        if not before_issues:
            continue
        candidates = reference_index[candidate_key(question)]
        ranked = sorted(
            ((similarity(question, candidate), candidate) for candidate in candidates),
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked:
            continue
        score, candidate = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        margin = score - runner_up
        if score < MIN_SCORE or margin < MIN_MARGIN:
            continue

        repaired = copy.deepcopy(question)
        repaired["content"] = candidate.get("content") or candidate.get("title")
        repaired["options"] = candidate.get("options")
        after_issues = question_quality_issues(repaired)
        record = {
            "line": line_number,
            "id": question.get("id"),
            "subject": question.get("subject"),
            "question_number": question.get("question_number"),
            "score": round(score, 4),
            "margin": round(margin, 4),
            "issues_before": before_issues,
            "issues_after": after_issues,
            "content_before": question.get("content") or question.get("title"),
            "content_after": repaired.get("content"),
        }
        if after_issues:
            skipped_after_validation.append(record)
            continue

        repaired["quality_restored_from"] = "question_bank_mcq.jsonl"
        repaired["quality_restore_confidence"] = round(score, 4)
        active[line_number - 1] = repaired
        restored.append(record)

    manifest = {
        "active_bank": str(ACTIVE_BANK.relative_to(ROOT)).replace("\\", "/"),
        "reference_bank": str(REFERENCE_BANK.relative_to(ROOT)).replace("\\", "/"),
        "minimum_similarity": MIN_SCORE,
        "minimum_margin": MIN_MARGIN,
        "dry_run": args.dry_run,
        "restored_count": len(restored),
        "skipped_after_validation_count": len(skipped_after_validation),
        "restored": restored,
        "skipped_after_validation": skipped_after_validation,
    }

    if not args.dry_run:
        if not BACKUP_BANK.exists():
            shutil.copy2(ACTIVE_BANK, BACKUP_BANK)
        write_jsonl(ACTIVE_BANK, active)
        MANIFEST_PATH.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(
        f"Restored {len(restored)} questions; "
        f"kept {len(skipped_after_validation)} questionable matches hidden."
    )


if __name__ == "__main__":
    main()
