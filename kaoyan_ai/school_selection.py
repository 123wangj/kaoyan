from __future__ import annotations

import hashlib
import json
import re
import statistics
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import urlparse
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from kaoyan_ai.agents.base import LLMClient


class SchoolSelectionRequest(BaseModel):
    school: str = Field(min_length=2, max_length=40)
    major: str = Field(default="计算机相关专业", min_length=2, max_length=60)
    historical_scores: list[float] = Field(default_factory=list, max_length=10)
    score_years: list[int] = Field(default_factory=list, max_length=10)
    target_score: float | None = Field(default=None, ge=0, le=500)

    @field_validator("historical_scores")
    @classmethod
    def validate_scores(cls, values: list[float]) -> list[float]:
        for value in values:
            if value < 100 or value > 500:
                raise ValueError("历史分数应在 100 到 500 之间")
        return values


class OnlineEvidence(BaseModel):
    title: str
    url: str
    snippet: str = ""
    source_type: str
    source_label: str
    query_type: str
    year: int | None = None
    score_mentions: list[int] = Field(default_factory=list)


@dataclass(frozen=True)
class SearchQuery:
    query_type: str
    text: str


_CACHE: dict[str, tuple[float, list[OnlineEvidence]]] = {}
_CACHE_LOCK = threading.RLock()
_CACHE_SECONDS = 6 * 60 * 60
_QWEN_WEB_TIMEOUT_SECONDS = 35
_FALLBACK_SEARCH_TIMEOUT_SECONDS = 12

OFFICIAL_DOMAINS = (
    "chsi.com.cn",
    "moe.gov.cn",
    "gov.cn",
)
INSTITUTION_DOMAINS = (
    "eol.cn",
    "kaoyan.com",
    "koolearn.com",
    "xdf.cn",
)


def _persistent_cache_path(cache_key: str) -> Path:
    from kaoyan_ai.config import get_settings

    directory = Path(get_settings().data_dir) / "school_selection_cache"
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return directory / f"{digest}.json"


def _read_persistent_cache(cache_key: str) -> list[OnlineEvidence] | None:
    path = _persistent_cache_path(cache_key)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(payload.get("created_at") or 0) >= _CACHE_SECONDS:
            return None
        return [
            OnlineEvidence.model_validate(item)
            for item in payload.get("evidence", [])
        ]
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _write_persistent_cache(
    cache_key: str,
    evidence: list[OnlineEvidence],
) -> None:
    path = _persistent_cache_path(cache_key)
    temp = path.with_suffix(".tmp")
    try:
        temp.write_text(
            json.dumps(
                {
                    "created_at": time.time(),
                    "evidence": [item.model_dump() for item in evidence],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        temp.replace(path)
    except OSError:
        pass


def analyze_school_selection(
    payload: SchoolSelectionRequest,
    *,
    search_provider: Callable[[str, int], list[dict[str, Any]]] | None = None,
    llm: "LLMClient | None" = None,
    learning_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = collect_online_evidence(payload, search_provider=search_provider)
    effective_payload = payload
    score_source = "user_input" if payload.historical_scores else "unavailable"
    if not payload.historical_scores:
        evidence_scores, evidence_years = _evidence_score_series(evidence)
        if evidence_scores:
            effective_payload = payload.model_copy(
                update={
                    "historical_scores": evidence_scores,
                    "score_years": evidence_years,
                }
            )
            score_source = "online_evidence"
    trend = _score_trend(
        effective_payload.historical_scores,
        effective_payload.score_years,
    )
    trend["source"] = score_source
    heat = _heat_proxy(evidence)
    institution = _institution_consensus(evidence)
    readiness = _learning_readiness(learning_profile)
    risk = _risk_assessment(effective_payload, trend, heat, institution, readiness)
    summary = _generate_summary(
        effective_payload,
        trend,
        heat,
        institution,
        readiness,
        risk,
        evidence,
        llm=llm,
    )
    return {
        "school": payload.school,
        "major": payload.major,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "trend": trend,
        "heat": heat,
        "institution_consensus": institution,
        "learning_readiness": readiness,
        "risk": risk,
        "summary": summary,
        "evidence": [item.model_dump() for item in evidence[:18]],
        "methodology": (
            "网络热度为公开网页关注度代理指标，综合近期结果数量、来源多样性、"
            "官方信息和机构讨论，不等同于真实报考人数或百度指数。个人适配度"
            "使用当前题库覆盖率、正确率和四科均衡度计算；历史分数优先联网获取，"
            "手动填写仅用于补充或纠正。"
        ),
        "disclaimer": (
            "仅供参考。招生计划、推免人数、专业课变化、复试权重和当年生源"
            "都会显著影响录取结果，请以研招网和院校研究生招生官网为准。"
        ),
    }


def _evidence_score_series(
    evidence: list[OnlineEvidence],
) -> tuple[list[float], list[int]]:
    """Extract a conservative year/score series from explicitly score-like sources."""

    by_year: dict[int, int] = {}
    score_terms = ("复试线", "最低分", "录取分数", "分数线")
    for item in evidence:
        if item.year is None or not item.score_mentions:
            continue
        text = f"{item.title} {item.snippet}"
        if item.query_type != "score" and not any(term in text for term in score_terms):
            continue
        if item.source_type not in {"official", "institution"}:
            continue
        # A snippet can mention several majors or years. Only accept a single
        # unambiguous score for automatic trend calculation.
        unique_scores = list(dict.fromkeys(item.score_mentions))
        if len(unique_scores) == 1:
            by_year[item.year] = unique_scores[0]
    years = sorted(by_year)[-6:]
    return [float(by_year[year]) for year in years], years


def collect_online_evidence(
    payload: SchoolSelectionRequest,
    *,
    search_provider: Callable[[str, int], list[dict[str, Any]]] | None = None,
) -> list[OnlineEvidence]:
    cache_key = f"{payload.school}|{payload.major}".lower()
    if search_provider is None:
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached and time.time() - cached[0] < _CACHE_SECONDS:
                return cached[1]
        persistent = _read_persistent_cache(cache_key)
        if persistent is not None:
            with _CACHE_LOCK:
                _CACHE[cache_key] = (time.time(), persistent)
            return persistent
    if search_provider is None:
        researched = _qwen_web_evidence(payload)
        if researched:
            with _CACHE_LOCK:
                _CACHE[cache_key] = (time.time(), researched)
            _write_persistent_cache(cache_key, researched)
            return researched
    provider = search_provider or _duckduckgo_search
    current_year = datetime.now().year
    queries = (
        SearchQuery(
            "official",
            f"site:edu.cn {payload.school} {payload.major} 硕士 招生简章 复试 拟录取 {current_year}",
        ),
        SearchQuery(
            "score",
            f"site:edu.cn {payload.school} {payload.major} 考研 复试线 录取最低分 {current_year}",
        ),
        SearchQuery(
            "institution",
            f"{payload.school} {payload.major} kaoyan 考研 难度 热度 预测",
        ),
        SearchQuery(
            "discussion",
            f"{payload.school} {payload.major} kaoyan 报考 热度 经验",
        ),
    )
    query_rows: dict[str, list[dict[str, Any]]] = {}
    executor = ThreadPoolExecutor(max_workers=len(queries), thread_name_prefix="school-search")
    futures = {
        executor.submit(provider, query.text, 7): query
        for query in queries
    }
    done, pending = wait(futures, timeout=_FALLBACK_SEARCH_TIMEOUT_SECONDS)
    for future in done:
        query = futures[future]
        try:
            query_rows[query.query_type] = future.result()
        except Exception:
            query_rows[query.query_type] = []
    for future in pending:
        future.cancel()
    executor.shutdown(wait=False, cancel_futures=True)

    results: list[OnlineEvidence] = []
    seen_urls: set[str] = set()
    for query in queries:
        rows = query_rows.get(query.query_type, [])
        for row in rows:
            url = str(row.get("href") or row.get("url") or "").strip()
            if not url or url in seen_urls or not url.startswith(("http://", "https://")):
                continue
            seen_urls.add(url)
            title = _clean_text(row.get("title"), 160)
            snippet = _clean_text(row.get("body") or row.get("snippet"), 360)
            source_type, source_label = _classify_source(url)
            combined = f"{title} {snippet}"
            if not _is_relevant_result(payload, title, snippet, url):
                continue
            results.append(
                OnlineEvidence(
                    title=title or urlparse(url).netloc,
                    url=url,
                    snippet=snippet,
                    source_type=source_type,
                    source_label=source_label,
                    query_type=query.query_type,
                    year=_extract_year(combined),
                    score_mentions=_extract_scores(combined),
                )
            )
    results.sort(key=_evidence_sort_key)
    if search_provider is None:
        with _CACHE_LOCK:
            _CACHE[cache_key] = (time.time(), results)
        _write_persistent_cache(cache_key, results)
    return results


def _qwen_web_evidence(payload: SchoolSelectionRequest) -> list[OnlineEvidence]:
    """Use Qwen's first-party web_search/web_extractor tools when configured."""

    from openai import OpenAI
    from kaoyan_ai.config import get_settings

    settings = get_settings()
    if settings.disable_llm:
        return []
    # Qwen's web_search/web_extractor tools are served by the official
    # DashScope compatible endpoint. The application's primary chat provider
    # may point at a custom MaaS gateway that supports text generation but not
    # these tool types, so web research must use the dedicated configuration.
    api_key = settings.dashscope_api_key
    base_url = settings.dashscope_base_url
    model = settings.dashscope_model
    if not api_key or "qwen" not in model.lower():
        return []
    prompt = f"""
搜索“{payload.school} {payload.major}”硕士研究生招生信息。返回最多 4 条真实结果：
优先院校官网或研招网，并尽量包含复试线、拟录取或教育机构趋势分析；
排除本科高考信息，不得虚构分数或报考人数。
只输出 JSON：
{{"sources":[{{"title":"标题","url":"完整URL","snippet":"相关摘要",
"query_type":"official|score|institution|discussion","year":2026}}]}}
"""
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=min(_QWEN_WEB_TIMEOUT_SECONDS, max(8, settings.llm_timeout_seconds)),
            max_retries=0,
        )
        response = client.responses.create(
            model=model,
            input=prompt,
            tools=[{"type": "web_search"}],
            extra_body={"enable_thinking": settings.dashscope_enable_thinking},
        )
        text = str(getattr(response, "output_text", "") or "")
        match = re.search(r"\{[\s\S]*\}", text)
        parsed = json.loads(match.group(0)) if match else {}
    except Exception:
        return []
    results: list[OnlineEvidence] = []
    seen: set[str] = set()
    for row in parsed.get("sources", [])[:20]:
        url = str(row.get("url") or "").strip()
        title = _clean_text(row.get("title"), 160)
        snippet = _clean_text(row.get("snippet"), 360)
        if (
            not url.startswith(("http://", "https://"))
            or url in seen
            or not _is_relevant_result(payload, title, snippet, url)
        ):
            continue
        seen.add(url)
        source_type, source_label = _classify_source(url)
        query_type = str(row.get("query_type") or "discussion")
        if query_type not in {"official", "score", "institution", "discussion"}:
            query_type = "discussion"
        combined = f"{title} {snippet}"
        results.append(
            OnlineEvidence(
                title=title or urlparse(url).netloc,
                url=url,
                snippet=snippet,
                source_type=source_type,
                source_label=source_label,
                query_type=query_type,
                year=int(row["year"]) if str(row.get("year") or "").isdigit() else _extract_year(combined),
                score_mentions=_extract_scores(combined),
            )
        )
    results.sort(key=_evidence_sort_key)
    return results


def _duckduckgo_search(query: str, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        rows = list(DDGS(timeout=8).text(query, max_results=limit))
    except Exception:
        rows = []
    if len(rows) >= 2:
        return rows
    return _bing_rss_search(query, limit)


def _bing_rss_search(query: str, limit: int) -> list[dict[str, Any]]:
    """No-key fallback using Bing's public RSS search representation."""

    url = "https://www.bing.com/search?" + urlencode(
        {"q": query, "format": "rss", "setlang": "zh-hans", "count": limit}
    )
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; KaoyanSchoolResearch/1.0)",
            "Accept": "application/rss+xml, application/xml;q=0.9",
        },
    )
    with urlopen(request, timeout=10) as response:
        root = ET.fromstring(response.read())
    rows: list[dict[str, Any]] = []
    for item in root.findall(".//item")[:limit]:
        rows.append(
            {
                "title": item.findtext("title") or "",
                "href": item.findtext("link") or "",
                "body": item.findtext("description") or "",
            }
        )
    return rows


def _classify_source(url: str) -> tuple[str, str]:
    domain = urlparse(url).netloc.lower().split(":")[0]
    if domain.endswith(".edu.cn"):
        return "official", "院校官网"
    if any(domain == value or domain.endswith(f".{value}") for value in OFFICIAL_DOMAINS):
        return "official", "官方招生平台"
    if any(domain == value or domain.endswith(f".{value}") for value in INSTITUTION_DOMAINS):
        return "institution", "教育机构"
    return "community", "公开讨论"


def _is_relevant_result(
    payload: SchoolSelectionRequest,
    title: str,
    snippet: str,
    url: str,
) -> bool:
    text = f"{title} {snippet} {url}".lower()
    school = payload.school.lower().replace("大学", "")
    major_terms = {
        payload.major.lower(),
        "计算机",
        "软件",
        "电子信息",
        "人工智能",
        "网络空间",
    }
    school_hit = len(school) >= 2 and school in text
    major_hit = any(term and term in text for term in major_terms)
    admission_hit = any(
        term in text
        for term in ("考研", "硕士", "研究生", "复试", "拟录取", "招生", "kaoyan", "graduate")
    )
    return school_hit and (major_hit or admission_hit)


def _score_trend(scores: list[float], years: list[int]) -> dict[str, Any]:
    if not scores:
        return {
            "data_sufficient": False,
            "scores": [],
            "years": [],
            "slope": None,
            "predicted_range": None,
            "message": "未提供历史分数，无法计算分数趋势。",
        }
    clean_years = years if len(years) == len(scores) else list(
        range(datetime.now().year - len(scores), datetime.now().year)
    )
    if len(scores) == 1:
        return {
            "data_sufficient": False,
            "scores": scores,
            "years": clean_years,
            "slope": None,
            "predicted_range": None,
            "message": "只有一年数据，不能可靠推断趋势。",
        }
    x_mean = statistics.mean(clean_years)
    y_mean = statistics.mean(scores)
    denominator = sum((year - x_mean) ** 2 for year in clean_years)
    slope = (
        sum((year - x_mean) * (score - y_mean) for year, score in zip(clean_years, scores))
        / max(denominator, 1)
    )
    predicted_mid = scores[-1] + slope
    volatility = statistics.pstdev(scores) if len(scores) > 1 else 0
    band = max(6.0, volatility * 1.25)
    return {
        "data_sufficient": len(scores) >= 3,
        "scores": [round(value, 1) for value in scores],
        "years": clean_years,
        "slope": round(slope, 2),
        "direction": "上升" if slope > 1 else "下降" if slope < -1 else "基本稳定",
        "predicted_range": [
            round(max(0, predicted_mid - band)),
            round(min(500, predicted_mid + band)),
        ],
        "volatility": round(volatility, 2),
        "message": "至少三年数据时区间更有参考意义。",
    }


def _heat_proxy(evidence: list[OnlineEvidence]) -> dict[str, Any]:
    if not evidence:
        return {
            "score": 0,
            "level": "数据不足",
            "result_count": 0,
            "recent_count": 0,
            "source_diversity": 0,
            "official_count": 0,
            "institution_count": 0,
        }
    current_year = datetime.now().year
    recent = sum(item.year is not None and item.year >= current_year - 1 for item in evidence)
    types = {item.source_type for item in evidence}
    official = sum(item.source_type == "official" for item in evidence)
    institution = sum(item.source_type == "institution" for item in evidence)
    raw = (
        min(36, len(evidence) * 2)
        + min(24, recent * 4)
        + len(types) * 8
        + min(12, institution * 3)
        + min(8, official * 2)
    )
    score = min(100, round(raw))
    level = "高关注" if score >= 70 else "中等关注" if score >= 40 else "低关注"
    return {
        "score": score,
        "level": level,
        "result_count": len(evidence),
        "recent_count": recent,
        "source_diversity": len(types),
        "official_count": official,
        "institution_count": institution,
    }


def _institution_consensus(evidence: list[OnlineEvidence]) -> dict[str, Any]:
    mentions = [
        score
        for item in evidence
        if item.source_type == "institution"
        for score in item.score_mentions
    ]
    if not mentions:
        return {
            "available": False,
            "sample_size": 0,
            "range": None,
            "median": None,
            "note": "未从机构公开摘要中提取到可核验的分数预测。",
        }
    return {
        "available": True,
        "sample_size": len(mentions),
        "range": [min(mentions), max(mentions)],
        "median": round(statistics.median(mentions)),
        "note": "仅为机构网页摘要中的分数提及，可能包含往年分数，不等于机构一致预测。",
    }


def _learning_readiness(profile: dict[str, Any] | None) -> dict[str, Any]:
    data = profile or {}
    attempted = max(0, int(data.get("total_answered") or 0))
    total_questions = max(0, int(data.get("total_questions") or 0))
    correct = max(0, min(attempted, int(data.get("total_correct") or 0)))
    accuracy = float(data.get("accuracy") or 0)
    progress = (
        round(attempted / total_questions * 100, 1)
        if total_questions
        else float(data.get("progress") or 0)
    )
    subjects = data.get("subjects") if isinstance(data.get("subjects"), dict) else {}
    normalized_subjects: dict[str, dict[str, Any]] = {}
    active_accuracies: list[float] = []
    for subject, raw in subjects.items():
        item = raw if isinstance(raw, dict) else {}
        subject_attempted = max(0, int(item.get("attempted") or 0))
        subject_total = max(0, int(item.get("total") or 0))
        subject_accuracy = float(item.get("accuracy") or 0)
        subject_progress = float(
            item.get("progress")
            if item.get("progress") is not None
            else item.get("mastery_score") or 0
        )
        normalized_subjects[str(subject)] = {
            "attempted": subject_attempted,
            "total": subject_total,
            "accuracy": round(subject_accuracy, 1),
            "progress": round(subject_progress, 1),
        }
        if subject_attempted:
            active_accuracies.append(subject_accuracy)

    if attempted <= 0:
        return {
            "available": False,
            "score": None,
            "level": "等待学习数据",
            "attempted": 0,
            "total_questions": total_questions,
            "correct": 0,
            "accuracy": 0.0,
            "progress": 0.0,
            "sample_confidence": 0.0,
            "signals": {},
            "weak_subjects": [],
            "unstarted_subjects": list(normalized_subjects),
            "subjects": normalized_subjects,
            "note": "完成一些题目后，系统会自动把进度和正确率加入择校判断。",
        }

    balance = (
        max(0.0, 100.0 - statistics.pstdev(active_accuracies) * 2)
        if len(active_accuracies) > 1
        else 65.0
    )
    coverage_component = min(100.0, progress * 2.5)
    signals = {
        key: data.get(key)
        for key in (
            "difficulty_weighted_accuracy",
            "recent_30d_attempts",
            "recent_30d_accuracy",
            "recent_trend_delta",
            "first_attempt_accuracy",
            "repeat_accuracy",
            "repeat_improvement",
            "review_recovery_rate",
            "speed_score",
            "retention_score",
            "plan_completion",
            "days_to_exam",
            "mock_average",
        )
        if data.get(key) is not None
    }
    weighted_components: list[tuple[float, float]] = [
        (accuracy, 0.32),
        (coverage_component, 0.20),
        (balance, 0.10),
    ]
    optional_weights = {
        "difficulty_weighted_accuracy": 0.10,
        "recent_30d_accuracy": 0.08,
        "speed_score": 0.05,
        "review_recovery_rate": 0.05,
        "retention_score": 0.06,
        "plan_completion": 0.04,
    }
    for key, weight in optional_weights.items():
        if data.get(key) is not None:
            weighted_components.append((float(data[key]), weight))
    denominator = sum(weight for _, weight in weighted_components)
    base_score = sum(value * weight for value, weight in weighted_components) / denominator
    trend_delta = float(data.get("recent_trend_delta") or 0)
    repeat_delta = float(data.get("repeat_improvement") or 0)
    score = round(max(0.0, min(100.0, base_score + trend_delta * 0.08 + repeat_delta * 0.04)))
    level = (
        "冲刺匹配"
        if score >= 80
        else "进阶提升"
        if score >= 65
        else "基础强化"
        if score >= 45
        else "起步积累"
    )
    active_subjects = [
        (subject, item)
        for subject, item in normalized_subjects.items()
        if item["attempted"] > 0
    ]
    weak_subjects = [
        subject
        for subject, _ in sorted(
            active_subjects,
            key=lambda pair: (pair[1]["accuracy"], pair[1]["progress"]),
        )[:2]
    ]
    unstarted = [
        subject
        for subject, item in normalized_subjects.items()
        if item["attempted"] == 0
    ]
    return {
        "available": True,
        "score": score,
        "level": level,
        "attempted": attempted,
        "total_questions": total_questions,
        "correct": correct,
        "accuracy": round(accuracy, 1),
        "progress": round(progress, 1),
        "balance": round(balance, 1),
        "sample_confidence": float(
            data.get("sample_confidence")
            if data.get("sample_confidence") is not None
            else round(min(0.95, 0.2 + attempted / 100), 2)
        ),
        "signals": signals,
        "weak_subjects": weak_subjects,
        "unstarted_subjects": unstarted,
        "subjects": normalized_subjects,
        "note": (
            "画像分综合覆盖率、难度加权正确率、近 30 天趋势、首做/重做、"
            "做题速度、复习改善、遗忘风险与计划执行；缺失信号不会按 0 分处罚。"
        ),
    }


def _risk_assessment(
    payload: SchoolSelectionRequest,
    trend: dict[str, Any],
    heat: dict[str, Any],
    institution: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    risk_score = 35
    reasons: list[str] = []
    slope = trend.get("slope")
    if isinstance(slope, (int, float)) and slope > 2:
        risk_score += min(20, round(slope * 2))
        reasons.append("近年分数呈上升趋势")
    if heat.get("score", 0) >= 70:
        risk_score += 18
        reasons.append("公开网络关注度代理指标较高")
    elif heat.get("score", 0) >= 40:
        risk_score += 9
        reasons.append("公开网络关注度处于中等区间")
    predicted = trend.get("predicted_range")
    if payload.target_score and predicted:
        margin = payload.target_score - predicted[1]
        if margin >= 10:
            risk_score -= 15
            reasons.append("目标分高于趋势区间上沿")
        elif margin < 0:
            risk_score += 20
            reasons.append("目标分低于趋势区间上沿")
    if not trend.get("data_sufficient"):
        risk_score += 8
        reasons.append("历史分数样本不足")
    if heat.get("result_count", 0) < 4:
        reasons.append("网络证据较少，热度置信度偏低")
    attempted = int(readiness.get("attempted") or 0)
    readiness_score = readiness.get("score")
    if attempted >= 10 and isinstance(readiness_score, (int, float)):
        if readiness_score < 45:
            risk_score += 15
            reasons.append("当前做题进度与正确率仍处于起步阶段")
        elif readiness_score < 60:
            risk_score += 8
            reasons.append("当前学习画像与目标院校仍有提升空间")
        elif readiness_score >= 80:
            risk_score -= 10
            reasons.append("当前学习画像对冲刺目标形成正向支撑")
        elif readiness_score >= 70:
            risk_score -= 5
            reasons.append("当前做题表现处于较稳健区间")
        if float(readiness.get("accuracy") or 0) < 60:
            risk_score += 7
            reasons.append("当前总体正确率低于 60%")
    elif attempted:
        reasons.append("做题样本较少，个人适配度暂按低置信度计算")
    else:
        reasons.append("暂无做题画像，尚未计入个人学习表现")
    risk_score = max(5, min(95, risk_score))
    level = "高风险" if risk_score >= 70 else "中等风险" if risk_score >= 40 else "相对稳妥"
    confidence = min(
        0.92,
        0.3
        + min(len(payload.historical_scores), 4) * 0.1
        + min(heat.get("result_count", 0), 10) * 0.025
        + min(float(readiness.get("sample_confidence") or 0), 1.0) * 0.12,
    )
    return {
        "score": risk_score,
        "level": level,
        "confidence": round(confidence, 2),
        "reasons": reasons or ["暂未发现明显升温信号"],
    }


def _generate_summary(
    payload: SchoolSelectionRequest,
    trend: dict[str, Any],
    heat: dict[str, Any],
    institution: dict[str, Any],
    readiness: dict[str, Any],
    risk: dict[str, Any],
    evidence: list[OnlineEvidence],
    *,
    llm: "LLMClient | None",
) -> str:
    system = (
        "你是计算机考研择校分析助手。只能根据提供的数据作答。"
        "必须区分官方信息、机构观点和公开讨论；网络热度不等于报考人数。"
        "输出包含：综合判断、分数趋势、热度解读、风险因素、下一步核验清单。"
        "必须写“仅供参考”，不得虚构招生人数、报录比或分数。"
    )
    compact_evidence = [
        {
            "title": item.title,
            "source_type": item.source_type,
            "year": item.year,
            "snippet": item.snippet[:180],
        }
        for item in evidence[:10]
    ]
    prompt = json.dumps(
        {
            "school": payload.school,
            "major": payload.major,
            "target_score": payload.target_score,
            "trend": trend,
            "heat_proxy": heat,
            "institution_mentions": institution,
            "learning_readiness": readiness,
            "risk": risk,
            "evidence": compact_evidence,
        },
        ensure_ascii=False,
    )
    # The default API path already spent its latency budget on sourced web
    # research. Keep the report deterministic and fast instead of making a
    # second external model call. Callers may still inject an LLM explicitly.
    if llm is None or not evidence:
        text = ""
    else:
        model = llm
        text = model.generate(system, prompt).strip()
    if "离线占位结果" not in text and "大模型服务暂时不可用" not in text and len(text) >= 80:
        if "仅供参考" not in text:
            text += "\n\n仅供参考，请以院校官网和研招网最新公告为准。"
        return text
    predicted = trend.get("predicted_range")
    trend_text = (
        f"历史数据推算区间约为 {predicted[0]}–{predicted[1]} 分"
        if predicted
        else "历史数据不足，暂不能给出可靠分数区间"
    )
    if trend.get("source") == "online_evidence":
        trend_text += "（由公开来源自动提取）"
    if readiness.get("available"):
        readiness_text = (
            f"- 已完成 {readiness['attempted']}/{readiness['total_questions']} 题，"
            f"题库覆盖率 {readiness['progress']}%，总体正确率 {readiness['accuracy']}%。\n"
            f"- 个人备考画像为 {readiness['score']}/100（{readiness['level']}）"
        )
        weak_subjects = readiness.get("weak_subjects") or []
        if weak_subjects:
            readiness_text += f"，当前优先补强：{'、'.join(weak_subjects)}"
        readiness_text += "。"
    else:
        readiness_text = "- 暂无足够做题记录；完成题目后将自动加入个人适配度判断。"
    return (
        f"## 综合判断\n\n{payload.school} {payload.major} 当前评估为"
        f"“{risk['level']}”，模型置信度约 {round(risk['confidence'] * 100)}%。\n\n"
        f"## 分数与热度\n\n- {trend_text}。\n"
        f"- 公开网络关注度代理为 {heat['score']}/100（{heat['level']}）。"
        "该值不是报考人数，也不是百度指数。\n\n"
        f"## 个人学习画像\n\n{readiness_text}\n\n"
        f"## 主要风险\n\n"
        + "\n".join(f"- {reason}" for reason in risk["reasons"])
        + "\n\n## 下一步核验\n\n"
        "- 核对院校招生目录、统招名额和推免人数。\n"
        "- 下载近三年复试名单与拟录取名单，统计中位分而非只看最低分。\n"
        "- 核对复试权重、专业课科目和是否存在缩招。\n\n"
        "仅供参考，请以院校官网和研招网最新公告为准。"
    )


def _extract_year(text: str) -> int | None:
    years = [int(value) for value in re.findall(r"20[12]\d", text)]
    return max(years) if years else None


def _extract_scores(text: str) -> list[int]:
    values = []
    for raw in re.findall(r"(?<!\d)([234]\d{2})(?!\d)", text):
        value = int(raw)
        if 200 <= value <= 450 and not 2010 <= value <= 2029:
            values.append(value)
    return list(dict.fromkeys(values))[:5]


def _clean_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _evidence_sort_key(item: OnlineEvidence) -> tuple[int, int, str]:
    priority = {"official": 0, "institution": 1, "community": 2}
    return (
        priority.get(item.source_type, 3),
        -(item.year or 0),
        item.title,
    )
