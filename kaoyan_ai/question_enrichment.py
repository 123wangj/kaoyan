from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from kaoyan_ai.agents.base import LLMClient


UNLABELED_KP = "未标注知识点"
UNLABELED_MARKERS = {UNLABELED_KP, "鏈爣娉ㄧ煡璇嗙偣", "未标注", "暂无"}
IMAGE_REQUIRED_RE = re.compile(
    r"(如下图|下图|如图|图所示|图示|图中所示|见图|根据(?:下|上)?图|所示的[^，。；]{0,16}图)"
)

_LOCK = threading.RLock()


def is_unlabeled_kp(value: object) -> bool:
    if not value:
        return True
    text = str(value).strip()
    return not text or text in UNLABELED_MARKERS or any(marker in text for marker in UNLABELED_MARKERS)


def needs_knowledge_enrichment(question: dict[str, Any]) -> bool:
    if question.get("knowledge_mapping_status") in {
        "pending_glm_review",
        "unmatched",
    }:
        return False
    points = question.get("knowledge_points") or []
    if not isinstance(points, list):
        return True
    return not points or any(is_unlabeled_kp(point) for point in points)


def question_needs_image(question: dict[str, Any]) -> bool:
    text = " ".join(
        str(question.get(key) or "")
        for key in ("content", "title")
    )
    return bool(IMAGE_REQUIRED_RE.search(text))


def question_has_image(question: dict[str, Any]) -> bool:
    images = question.get("images")
    return bool(question.get("image_url") or question.get("image") or (isinstance(images, list) and images))


def question_is_displayable(question: dict[str, Any]) -> bool:
    """Hide image-dependent questions until a local/source image is available."""
    return not question_needs_image(question) or question_has_image(question)


def enrich_question_knowledge(question: dict[str, Any], data_dir: Path, persist: bool = True) -> dict[str, Any]:
    if not needs_knowledge_enrichment(question):
        if not question.get("knowledge_detail"):
            question["knowledge_detail"] = _fallback_detail(question, question.get("knowledge_points") or [])
        return question

    points, detail = _infer_knowledge_with_llm(question)
    if not points:
        points = _fallback_knowledge_points(question)
    if not detail:
        detail = _fallback_detail(question, points)

    question["knowledge_points"] = points[:5]
    question["knowledge_detail"] = detail
    question["knowledge_enriched_by"] = "llm" if points else "fallback"

    if persist and question.get("id"):
        update_question_jsonl(data_dir / "question_bank.jsonl", str(question["id"]), {
            "knowledge_points": question["knowledge_points"],
            "knowledge_detail": question["knowledge_detail"],
            "knowledge_enriched_by": question["knowledge_enriched_by"],
        })
    return question


def ensure_question_image(question: dict[str, Any], static_dir: Path, persist_data_dir: Path | None = None) -> dict[str, Any] | None:
    if question_has_image(question):
        _normalize_image_fields(question)
        return question
    if not question_needs_image(question):
        return question

    image_url = _lookup_cached_image(question, static_dir)
    if not image_url:
        image_url = _search_and_cache_image(question, static_dir)
    if not image_url:
        return None

    question["image_url"] = image_url
    question["images"] = [image_url]
    question["image_source"] = "cached_web_search"
    if persist_data_dir and question.get("id"):
        update_question_jsonl(persist_data_dir / "question_bank.jsonl", str(question["id"]), {
            "image_url": image_url,
            "images": [image_url],
            "image_source": "cached_web_search",
        })
    return question


def update_question_jsonl(path: Path, question_id: str, updates: dict[str, Any]) -> bool:
    if not path.exists() or not question_id:
        return False
    with _LOCK:
        rows: list[dict[str, Any]] = []
        changed = False
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(row.get("id")) == question_id:
                    row.update(updates)
                    changed = True
                rows.append(row)
        if not changed:
            return False
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
        return True


def _infer_knowledge_with_llm(question: dict[str, Any]) -> tuple[list[str], str]:
    system_prompt = (
        "你是计算机考研408题目知识点标注专家。"
        "请根据题干、选项、解析判断最具体的知识点，并补充一段可用于每日复习的知识点讲解。"
        "只输出JSON，格式为："
        '{"knowledge_points":["具体知识点1","具体知识点2"],"knowledge_detail":"120到220字中文讲解"}。'
    )
    options = "\n".join(str(x) for x in (question.get("options") or []))
    user_prompt = f"""
科目：{question.get("subject") or ""}
章节：{question.get("chapter") or ""}
小节：{question.get("section") or ""}
题干：{question.get("content") or question.get("title") or ""}
选项：{options}
答案：{question.get("answer") or ""}
解析：{question.get("explanation") or question.get("analysis") or ""}
"""
    try:
        text = LLMClient().generate(system_prompt, user_prompt)
        match = re.search(r"\{[\s\S]*\}", text or "")
        if not match:
            return [], ""
        data = json.loads(match.group(0))
        points = [str(p).strip() for p in data.get("knowledge_points", []) if str(p).strip()]
        points = [p for p in points if not is_unlabeled_kp(p)]
        detail = str(data.get("knowledge_detail") or "").strip()
        return points[:5], detail
    except Exception:
        return [], ""


def _fallback_knowledge_points(question: dict[str, Any]) -> list[str]:
    text = str(question.get("explanation") or question.get("analysis") or question.get("content") or "")
    patterns = [
        r"[【\[]考点[】\]]\s*[:：]?\s*([^。\n；;]{2,40})",
        r"本题考查\s*([^。\n；;]{2,40})",
        r"考查\s*([^。\n；;]{2,40})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            raw = re.split(r"[、,，/；;]", match.group(1))
            points = []
            for item in raw:
                point = re.sub(r"^(的?是|关于|对|对于)", "", item.strip(" ：:。"))
                point = point.strip(" ：:。")
                if point:
                    points.append(point)
            if points:
                return points[:4]
    for key in ("section", "chapter"):
        value = str(question.get(key) or "").strip()
        if value:
            return [re.sub(r"^第\s*\d+\s*章\s*", "", value).strip()]
    subject = str(question.get("subject") or "").strip()
    return [f"{subject}基础考点" if subject else UNLABELED_KP]


def _fallback_detail(question: dict[str, Any], points: list[str]) -> str:
    base = "、".join(points[:3]) if points else str(question.get("section") or question.get("chapter") or "本题考点")
    explanation = str(question.get("explanation") or question.get("analysis") or "").strip()
    if explanation:
        return f"{base}：{explanation[:220]}"
    return f"{base}：请结合题干、选项和教材对应章节复习定义、适用条件、典型解法与易错点。"


def _normalize_image_fields(question: dict[str, Any]) -> None:
    image = question.get("image_url") or question.get("image")
    if image and not question.get("image_url"):
        question["image_url"] = image
    if image and not question.get("images"):
        question["images"] = [image]


def _lookup_cached_image(question: dict[str, Any], static_dir: Path) -> str | None:
    qid = _safe_id(str(question.get("id") or ""))
    if not qid:
        return None
    image_dir = static_dir / "question_images"
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        path = image_dir / f"{qid}{ext}"
        if path.exists() and path.stat().st_size > 1024:
            return f"/static/question_images/{path.name}"
    return None


def _search_and_cache_image(question: dict[str, Any], static_dir: Path) -> str | None:
    if os.environ.get("DISABLE_QUESTION_IMAGE_SEARCH", "").lower() in {"1", "true", "yes"}:
        return None
    qid = _safe_id(str(question.get("id") or ""))
    if not qid:
        return None
    try:
        from duckduckgo_search import DDGS
    except Exception:
        return None

    query = _image_search_query(question)
    keywords = _image_keywords(question)
    try:
        with DDGS(timeout=8) as ddgs:
            results = list(ddgs.images(query, max_results=8))
    except Exception:
        return None

    for item in results:
        if not _is_confident_image_result(item, keywords):
            continue
        url = item.get("image") or item.get("thumbnail")
        if not url:
            continue
        saved = _download_image(url, static_dir / "question_images", qid)
        if saved:
            return f"/static/question_images/{saved.name}"
    return None


def _image_search_query(question: dict[str, Any]) -> str:
    content = re.sub(r"\s+", " ", str(question.get("content") or question.get("title") or ""))
    source = str(question.get("source") or "")
    number = str(question.get("question_number") or "")
    subject = str(question.get("subject") or "")
    return f"{source} {number} {subject} {content[:70]} 题图"


def _image_keywords(question: dict[str, Any]) -> set[str]:
    text = " ".join(str(question.get(key) or "") for key in ("content", "source", "subject"))
    tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", text)
    useful = [t for t in tokens if t not in {"下列", "正确", "的是", "题图", "考研", "选择"}]
    return set(useful[:8])


def _is_confident_image_result(item: dict[str, Any], keywords: set[str]) -> bool:
    haystack = " ".join(str(item.get(k) or "") for k in ("title", "url", "source", "image")).lower()
    if not any(marker in haystack for marker in ("408", "王道", "kaoyan", "考研", "真题")):
        return False
    hits = sum(1 for keyword in keywords if keyword.lower() in haystack)
    return hits >= 1


def _download_image(url: str, image_dir: Path, qid: str) -> Path | None:
    image_dir.mkdir(parents=True, exist_ok=True)
    parsed = urllib.parse.urlparse(url)
    ext = Path(parsed.path).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ext = ".jpg"
    target = image_dir / f"{qid}{ext}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type:
                return None
            data = resp.read(2_500_000)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    if len(data) < 1024:
        return None
    target.write_bytes(data)
    return target


def _safe_id(value: str) -> str:
    if not value:
        return ""
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("._")
    if len(safe) <= 90:
        return safe
    digest = hashlib.md5(value.encode("utf-8")).hexdigest()[:12]
    return f"{safe[:70]}-{digest}"
