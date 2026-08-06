"""Extract question snippets with diagrams from the original Wangdao PDFs.

The normalized question-bank PDFs in ``tiku/`` no longer contain their source
figures.  This script locates the corresponding question in the scanned
Wangdao books, crops the complete source question block (stem, diagram and
options), and writes local image URLs back to ``data/question_bank.jsonl``.

Usage:
    python scripts/extract_question_images.py
    python scripts/extract_question_images.py --subject 数据结构 --limit 3
    python scripts/extract_question_images.py --dry-run
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz
from PIL import Image
from rapidocr_onnxruntime import RapidOCR


ROOT = Path(__file__).resolve().parents[1]
QUESTION_BANK = ROOT / "data" / "question_bank.jsonl"
BACKUP_BANK = ROOT / "data" / "question_bank.before_images.jsonl"
IMAGE_DIR = ROOT / "static" / "question_images"
MANIFEST_PATH = ROOT / "data" / "question_image_manifest.json"
CACHE_PATH = ROOT / "tmp" / "pdfs" / "question_image_ocr_cache.json"

IMAGE_REFERENCE_RE = re.compile(
    r"(如下图|下图|如图|图所示|图示|图中所示|见图|根据(?:下|上)?图|所示的[^，。；]{0,16}图)"
)
QUESTION_START_RE = re.compile(r"^\s*0?(\d{1,3})\s*[.．、]")
SECTION_RE = re.compile(r"(\d+\.\d+)")

# The composition-principles scan has no PDF outline.  Page range is filled
# after inspecting its table of contents; values are 1-based physical pages.
OUTLINELESS_SECTION_RANGES: dict[str, dict[str, tuple[int, int]]] = {
    "计算机组成原理": {
        "3.2": (96, 110),
    }
}


@dataclass
class OCRLine:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    confidence: float


@dataclass
class QuestionBlock:
    page_number: int
    number: str
    y0: float
    y1: float
    text: str


def eprint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    temp_path = path.with_suffix(path.suffix + ".images.tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    temp_path.replace(path)


def normalize_text(value: object) -> str:
    text = str(value or "").lower()
    text = re.sub(r"【\d{4}\s*统考真题】", "", text)
    text = re.sub(r"[\W_]+", "", text, flags=re.UNICODE)
    return text


def question_key(question: dict[str, Any]) -> str:
    """Return a stable key even when legacy IDs collide across subjects."""
    raw = "|".join(
        (
            str(question.get("subject") or ""),
            str(question.get("id") or ""),
            normalize_text(question.get("content") or question.get("title"))[:220],
        )
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def ngrams(text: str, size: int = 2) -> set[str]:
    if len(text) <= size:
        return {text} if text else set()
    return {text[index : index + size] for index in range(len(text) - size + 1)}


def similarity(question: dict[str, Any], block: QuestionBlock) -> float:
    target = normalize_text(question.get("content") or question.get("title"))
    found = normalize_text(block.text)
    if not target or not found:
        return 0.0

    # The source scan and normalized bank can differ in punctuation, spacing,
    # edition wording and OCR quality.  Combining sequence and n-gram scores is
    # more stable than requiring an exact substring.
    target_head = target[:180]
    found_head = found[:500]
    seq = difflib.SequenceMatcher(None, target_head, found_head).ratio()
    a, b = ngrams(target_head), ngrams(found_head)
    jaccard = len(a & b) / max(1, len(a | b))
    containment = len(a & b) / max(1, len(a))
    score = max(seq, 0.45 * jaccard + 0.55 * containment)

    expected_number = str(question.get("question_number") or "").lstrip("0")
    found_number = str(block.number or "").lstrip("0")
    if expected_number and expected_number == found_number:
        score += 0.08
    return min(score, 1.0)


def minimum_match_score(question: dict[str, Any]) -> float:
    """Allow narrowly-scoped lower scores for badly garbled legacy stems."""
    raw = str(question.get("content") or question.get("title") or "")
    text = normalize_text(raw)
    if "2016" in raw and "hub再生比特流" in text:
        return 0.25
    if "2017" in raw and "ieee80211数据帧f" in text:
        return 0.44
    return 0.50


def identify_books() -> dict[str, Path]:
    books: dict[str, Path] = {}
    for path in (ROOT / "wangdao").glob("*.pdf"):
        name = path.name
        if "数据结构" in name:
            books["数据结构"] = path
        elif "组成原理" in name:
            books["计算机组成原理"] = path
        elif "计算机网络" in name:
            books["计算机网络"] = path
        elif "操作系统" in name:
            books["操作系统"] = path
    return books


def section_id(question: dict[str, Any]) -> str:
    for value in (question.get("section"), question.get("chapter")):
        match = SECTION_RE.search(str(value or ""))
        if match:
            return match.group(1)
    return ""


def effective_section_id(question: dict[str, Any]) -> str:
    """Correct known legacy section labels using the question's knowledge topic."""
    section = section_id(question)
    subject = str(question.get("subject") or "")
    text = normalize_text(question.get("content") or question.get("title"))
    if subject == "数据结构":
        if "强连通分量" in text:
            return "6.1"
        if "dijkstra" in text:
            return "6.4"
        if "平衡二叉树" in text:
            return "7.3"
    elif subject == "计算机网络":
        if "分组交换网络" in text and "时延带宽积" in text:
            return "1.1"
        if "曼彻斯特" in text:
            return "2.1"
        if "ieee80211" in text or "csma/ca" in text or "hub再生比特流" in text:
            return "3.6"
        if "以太网拓扑" in text or "冲突域" in text:
            return "3.8"
        if "rip交换路由" in text:
            return "4.4"
        if "电子邮件" in text:
            return "6.4"
    return section


def section_quiz_range(doc: fitz.Document, section: str) -> tuple[int, int] | None:
    """Return inclusive 1-based physical page range containing quiz questions."""
    toc = doc.get_toc()
    section_index: int | None = None
    section_level: int | None = None
    for index, (level, title, _page) in enumerate(toc):
        match = SECTION_RE.search(title)
        if match and match.group(1) == section and level <= 2:
            section_index = index
            section_level = level
            break
    if section_index is None or section_level is None:
        return None

    quiz_start: int | None = None
    answer_start: int | None = None
    section_end: int | None = None
    for level, title, page in toc[section_index + 1 :]:
        if level <= section_level:
            section_end = page - 1
            break
        compact = re.sub(r"\s+", "", title)
        if quiz_start is None and ("试题精选" in compact or "习题精选" in compact):
            quiz_start = page
        elif quiz_start is not None and "答案与解析" in compact:
            answer_start = page
            break

    if quiz_start is None:
        return None
    # PDF bookmarks frequently point to a page where the final quiz questions
    # occupy the top half and the answer section begins below them.  Include
    # that page, plus one page before the quiz bookmark to cover imprecise
    # outline destinations.
    quiz_start = max(1, quiz_start - 1)
    end = answer_start if answer_start else section_end
    if end is None:
        end = min(len(doc), quiz_start + 12)
    return quiz_start, max(quiz_start, end)


def load_cache() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(cache: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = CACHE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(CACHE_PATH)


def page_cache_key(pdf_path: Path, page_number: int, scale: float) -> str:
    stat = pdf_path.stat()
    return f"{pdf_path.name}|{stat.st_size}|{int(stat.st_mtime)}|{page_number}|{scale}"


def ocr_page(
    doc: fitz.Document,
    pdf_path: Path,
    page_number: int,
    engine: RapidOCR,
    cache: dict[str, Any],
    scale: float = 1.55,
) -> tuple[list[OCRLine], float]:
    key = page_cache_key(pdf_path, page_number, scale)
    cached = cache.get(key)
    if isinstance(cached, dict) and isinstance(cached.get("lines"), list):
        return [OCRLine(**line) for line in cached["lines"]], float(cached["scale"])

    page = doc[page_number - 1]
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    result, _elapsed = engine(pixmap.tobytes("png"))
    lines: list[OCRLine] = []
    for item in result or []:
        polygon, text, confidence = item
        xs = [float(point[0]) for point in polygon]
        ys = [float(point[1]) for point in polygon]
        lines.append(
            OCRLine(
                x0=min(xs),
                y0=min(ys),
                x1=max(xs),
                y1=max(ys),
                text=str(text),
                confidence=float(confidence),
            )
        )
    lines.sort(key=lambda line: (line.y0, line.x0))
    cache[key] = {
        "scale": scale,
        "lines": [line.__dict__ for line in lines],
    }
    save_cache(cache)
    return lines, scale


def question_blocks(
    lines: list[OCRLine],
    page_number: int,
    page_height_pixels: float,
) -> list[QuestionBlock]:
    starts: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if line.x0 > 0.34 * max((item.x1 for item in lines), default=1):
            continue
        match = QUESTION_START_RE.match(line.text)
        # Reject IP addresses such as "201.1.1.0/24", which OCR can place at
        # the left margin and otherwise mistake for question 201.
        if match and 1 <= int(match.group(1)) <= 120:
            starts.append((index, match.group(1)))

    blocks: list[QuestionBlock] = []
    for start_index, (line_index, number) in enumerate(starts):
        next_line_index = starts[start_index + 1][0] if start_index + 1 < len(starts) else len(lines)
        selected = lines[line_index:next_line_index]
        if not selected:
            continue
        y0 = min(line.y0 for line in selected)
        y1 = (
            min(lines[next_line_index].y0 - 4, page_height_pixels)
            if next_line_index < len(lines)
            else page_height_pixels - 22
        )
        text = " ".join(line.text for line in selected)
        blocks.append(
            QuestionBlock(
                page_number=page_number,
                number=number,
                y0=y0,
                y1=max(y0 + 24, y1),
                text=text,
            )
        )
    return blocks


def crop_question(
    doc: fitz.Document,
    block: QuestionBlock,
    ocr_scale: float,
    output_path: Path,
    render_scale: float = 2.2,
) -> None:
    page = doc[block.page_number - 1]
    top = max(page.rect.y0, block.y0 / ocr_scale - 7)
    # Figures are often placed to the right of the stem and extend slightly
    # below the OCR-detected start of the next question.  Keep a generous
    # lower safety margin so tree leaves, arrow heads and axis labels are not
    # clipped.
    bottom = min(page.rect.y1 - 16, block.y1 / ocr_scale + 48)
    clip = fitz.Rect(page.rect.x0 + 34, top, page.rect.x1 - 34, bottom)
    pixmap = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale), clip=clip, alpha=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(output_path)


def crop_cross_page_question(
    doc: fitz.Document,
    block: QuestionBlock,
    ocr_scale: float,
    output_path: Path,
    next_page_lines: list[OCRLine],
    next_page_scale: float,
    render_scale: float = 2.2,
) -> None:
    """Crop a question that starts at a page bottom and continues next page."""
    page = doc[block.page_number - 1]
    first_clip = fitz.Rect(
        page.rect.x0 + 34,
        max(page.rect.y0, block.y0 / ocr_scale - 7),
        page.rect.x1 - 34,
        page.rect.y1 - 16,
    )
    first_pix = page.get_pixmap(
        matrix=fitz.Matrix(render_scale, render_scale),
        clip=first_clip,
        alpha=False,
    )
    first = Image.frombytes("RGB", (first_pix.width, first_pix.height), first_pix.samples)

    next_page = doc[block.page_number]
    first_real_question_y: float | None = None
    page_width_pixels = next_page.rect.width * next_page_scale
    for line in next_page_lines:
        match = QUESTION_START_RE.match(line.text)
        if (
            match
            and 1 <= int(match.group(1)) <= 120
            and line.x0 < page_width_pixels * 0.34
        ):
            first_real_question_y = line.y0 / next_page_scale
            break
    if first_real_question_y is None:
        first_real_question_y = min(next_page.rect.y1 - 16, next_page.rect.y0 + 230)

    second_clip = fitz.Rect(
        next_page.rect.x0 + 34,
        next_page.rect.y0 + 42,
        next_page.rect.x1 - 34,
        max(next_page.rect.y0 + 70, first_real_question_y - 7),
    )
    second_pix = next_page.get_pixmap(
        matrix=fitz.Matrix(render_scale, render_scale),
        clip=second_clip,
        alpha=False,
    )
    second = Image.frombytes("RGB", (second_pix.width, second_pix.height), second_pix.samples)
    width = max(first.width, second.width)
    combined = Image.new("RGB", (width, first.height + second.height), "white")
    combined.paste(first, (0, 0))
    combined.paste(second, (0, first.height))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.save(output_path)


def safe_filename(question: dict[str, Any]) -> str:
    question_id = str(question.get("id") or "")
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", question_id).strip("._")
    digest = question_key(question)[:10]
    return f"{(safe or 'question')[:100]}-{digest}.png"


def find_matches(
    questions: list[dict[str, Any]],
    book_path: Path,
    section: str,
    engine: RapidOCR,
    cache: dict[str, Any],
) -> tuple[list[tuple[dict[str, Any], QuestionBlock, float, float]], list[dict[str, Any]]]:
    with fitz.open(book_path) as doc:
        page_range = section_quiz_range(doc, section)
        if page_range is None:
            page_range = OUTLINELESS_SECTION_RANGES.get(questions[0]["subject"], {}).get(section)
        if page_range is None:
            return [], [
                {
                    "id": q.get("id"),
                    "reason": "section_range_not_found",
                    "section": section,
                }
                for q in questions
            ]

        start_page, end_page = page_range
        end_page = min(end_page, len(doc))
        eprint(
            f"[{questions[0]['subject']} {section}] OCR pages "
            f"{start_page}-{end_page} for {len(questions)} candidate(s)"
        )
        all_blocks: list[tuple[QuestionBlock, float]] = []
        for page_number in range(start_page, end_page + 1):
            eprint(f"  OCR {book_path.name} page {page_number}/{len(doc)}")
            lines, scale = ocr_page(doc, book_path, page_number, engine, cache)
            page_height_pixels = doc[page_number - 1].rect.height * scale
            all_blocks.extend((block, scale) for block in question_blocks(lines, page_number, page_height_pixels))

        matches: list[tuple[dict[str, Any], QuestionBlock, float, float]] = []
        failures: list[dict[str, Any]] = []
        claimed: set[tuple[int, float]] = set()
        for question in questions:
            ranked = sorted(
                (
                    (similarity(question, block), block, scale)
                    for block, scale in all_blocks
                    if (block.page_number, block.y0) not in claimed
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            if not ranked or ranked[0][0] < minimum_match_score(question):
                best = ranked[0][0] if ranked else 0.0
                failures.append(
                    {
                        "id": question.get("id"),
                        "question_key": question_key(question),
                        "subject": question.get("subject"),
                        "reason": "low_match_score",
                        "best_score": round(best, 4),
                        "section": section,
                    }
                )
                continue
            score, block, scale = ranked[0]
            claimed.add((block.page_number, block.y0))
            matches.append((question, block, score, scale))
        return matches, failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", help="Only process one subject")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of unique questions")
    parser.add_argument("--dry-run", action="store_true", help="OCR and match without writing files")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-extract images previously created by this script",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = load_jsonl(QUESTION_BANK)
    previous_urls: set[str] = set()
    if args.refresh:
        for row in rows:
            if row.get("image_source") != "wangdao_pdf_crop":
                continue
            previous_url = str(row.get("image_url") or "")
            if previous_url:
                previous_urls.add(previous_url)
            row.pop("image_url", None)
            row.pop("images", None)
            row.pop("image_source", None)

    candidates_by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        question_id = str(row.get("id") or "")
        content = str(row.get("content") or row.get("title") or "")
        if not question_id or not IMAGE_REFERENCE_RE.search(content):
            continue
        if args.subject and row.get("subject") != args.subject:
            continue
        has_image = bool(row.get("image_url") or row.get("image") or row.get("images"))
        if has_image and not (args.refresh and row.get("image_source") == "wangdao_pdf_crop"):
            continue
        candidates_by_key.setdefault(question_key(row), row)

    candidates = list(candidates_by_key.values())
    if args.limit > 0:
        candidates = candidates[: args.limit]
    eprint(f"Found {len(candidates)} unique image-dependent question(s)")
    if not candidates:
        return 0

    books = identify_books()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    failures: list[dict[str, Any]] = []
    for question in candidates:
        subject = str(question.get("subject") or "")
        section = effective_section_id(question)
        if subject not in books:
            failures.append({"id": question.get("id"), "reason": "book_not_found"})
        elif not section:
            failures.append({"id": question.get("id"), "reason": "section_not_found"})
        else:
            grouped[(subject, section)].append(question)

    engine = RapidOCR()
    cache = load_cache()
    manifest_matches: list[dict[str, Any]] = []
    updates: dict[str, str] = {}
    matched_questions: list[tuple[dict[str, Any], str, dict[str, Any]]] = []

    for (subject, section), questions in grouped.items():
        matches, group_failures = find_matches(
            questions,
            books[subject],
            section,
            engine,
            cache,
        )
        failures.extend(group_failures)
        if args.dry_run:
            for question, block, score, _scale in matches:
                eprint(
                    f"  DRY MATCH {question['id']} -> page {block.page_number} "
                    f"Q{block.number}, score={score:.3f}"
                )
            continue

        with fitz.open(books[subject]) as doc:
            for question, block, score, scale in matches:
                filename = safe_filename(question)
                output_path = IMAGE_DIR / filename
                is_cross_page = (
                    subject == "计算机网络"
                    and str(question.get("id") or "")
                    in {
                        "wd-mcq-计算机-024-41",
                        "wd-mcq-计算机-042-63",
                    }
                    and block.page_number < len(doc)
                )
                if is_cross_page:
                    next_lines, next_scale = ocr_page(
                        doc,
                        books[subject],
                        block.page_number + 1,
                        engine,
                        cache,
                    )
                    crop_cross_page_question(
                        doc,
                        block,
                        scale,
                        output_path,
                        next_lines,
                        next_scale,
                    )
                else:
                    crop_question(doc, block, scale, output_path)
                image_url = f"/static/question_images/{filename}"
                updates[question_key(question)] = image_url
                match_record = {
                    "id": question["id"],
                    "question_key": question_key(question),
                    "subject": subject,
                    "section": section,
                    "source_pdf": books[subject].name,
                    "source_page": block.page_number,
                    "source_question_number": block.number,
                    "match_score": round(score, 4),
                    "image_url": image_url,
                }
                manifest_matches.append(match_record)
                matched_questions.append((question, image_url, match_record))
                eprint(
                    f"  SAVED {question['id']} -> {filename} "
                    f"(page {block.page_number}, score={score:.3f})"
                )

    # Some normalized banks contain the same true-exam question twice under
    # different legacy IDs. Reuse the already verified local crop only when
    # the normalized stems are nearly identical and the subject is the same.
    unresolved = [q for q in candidates if question_key(q) not in updates]
    for question in unresolved:
        target = normalize_text(question.get("content") or question.get("title"))
        ranked_duplicates: list[tuple[float, dict[str, Any], str, dict[str, Any]]] = []
        for matched_question, image_url, source_record in matched_questions:
            if matched_question.get("subject") != question.get("subject"):
                continue
            candidate_text = normalize_text(
                matched_question.get("content") or matched_question.get("title")
            )
            score = difflib.SequenceMatcher(None, target, candidate_text).ratio()
            ranked_duplicates.append((score, matched_question, image_url, source_record))
        if not ranked_duplicates:
            continue
        score, _matched_question, image_url, source_record = max(
            ranked_duplicates, key=lambda item: item[0]
        )
        if score < 0.82:
            continue
        updates[question_key(question)] = image_url
        manifest_matches.append(
            {
                "id": question["id"],
                "question_key": question_key(question),
                "subject": question.get("subject"),
                "section": effective_section_id(question),
                "source_pdf": source_record["source_pdf"],
                "source_page": source_record["source_page"],
                "source_question_number": source_record["source_question_number"],
                "match_score": round(score, 4),
                "image_url": image_url,
                "reused_from_question_key": source_record["question_key"],
            }
        )
        failures = [
            failure
            for failure in failures
            if failure.get("question_key") != question_key(question)
        ]
        eprint(
            f"  REUSED {question['id']} from an equivalent question "
            f"(score={score:.3f})"
        )

    if args.dry_run:
        eprint(f"Dry run complete; failures={len(failures)}")
        return 0

    if updates:
        if not BACKUP_BANK.exists():
            shutil.copy2(QUESTION_BANK, BACKUP_BANK)
        for row in rows:
            image_url = updates.get(question_key(row))
            if image_url:
                row["image_url"] = image_url
                row["images"] = [image_url]
                row["image_source"] = "wangdao_pdf_crop"
        write_jsonl(QUESTION_BANK, rows)

        current_urls = set(updates.values())
        for old_url in previous_urls - current_urls:
            old_path = (ROOT / old_url.lstrip("/")).resolve()
            if old_path.parent == IMAGE_DIR.resolve() and old_path.exists():
                old_path.unlink()

    manifest = {
        "matched_count": len(manifest_matches),
        "failure_count": len(failures),
        "matches": manifest_matches,
        "failures": failures,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    eprint(
        f"Done: matched={len(manifest_matches)}, failed={len(failures)}, "
        f"manifest={MANIFEST_PATH}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
