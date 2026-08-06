from __future__ import annotations

import re
from typing import Any


# CJK Extension-A characters do not normally occur in these simplified-Chinese
# exam questions. They, private-use characters and U+FFFD are reliable signs of
# broken PDF font decoding.
GARBLED_TEXT_RE = re.compile(r"[\u3400-\u4dbf\ue000-\uf8ff\ufffd]")
OPTION_LABEL_RE = re.compile(r"^\s*([A-D])(?:[.．、:：\s]|$)", re.IGNORECASE)
EXTRA_OPTION_LABEL_RE = re.compile(r"\s[E-H](?:[.．、:：\s]|$)", re.IGNORECASE)
DAMAGED_SOURCE_RE = re.compile(
    r"(?:题干|原题(?:题干)?)(?:虽有|存在|有|已经|可能)?"
    r"(?:明显)?(?:残缺|缺失|不完整|截断)"
    r"|根据经典考研题库可知原题"
)
TRUNCATED_STEM_RE = re.compile(
    r"^\s*(?:为最高优先级(?:。|，|,|\s)|ms(?:，|,|\s))",
    re.IGNORECASE,
)


def question_quality_issues(question: dict[str, Any]) -> list[str]:
    """Return only high-confidence structural/source damage signals."""
    issues: list[str] = []
    if question.get("quality_status") == "unrecoverable_alignment":
        issues.append("unrecoverable_alignment")
    content = str(question.get("content") or question.get("title") or "").strip()
    options = question.get("options") or []
    explanation = str(question.get("explanation") or question.get("analysis") or "")
    searchable = " ".join([content, explanation, *(str(item) for item in options)])

    if not content:
        issues.append("missing_stem")
    elif TRUNCATED_STEM_RE.search(content):
        issues.append("damaged_source")
    if GARBLED_TEXT_RE.search(searchable):
        issues.append("garbled_text")

    if str(question.get("type") or "").lower() == "choice":
        if not isinstance(options, list) or len(options) != 4:
            issues.append("invalid_option_count")
        else:
            labels = []
            for option in options:
                match = OPTION_LABEL_RE.match(str(option))
                labels.append(match.group(1).upper() if match else None)
            if labels != ["A", "B", "C", "D"]:
                issues.append("invalid_option_labels")
            elif any(EXTRA_OPTION_LABEL_RE.search(str(option)) for option in options):
                issues.append("invalid_option_count")

    if DAMAGED_SOURCE_RE.search(explanation):
        issues.append("damaged_source")

    return issues


def question_is_well_formed(question: dict[str, Any]) -> bool:
    return not question_quality_issues(question)
