from __future__ import annotations

import math
import re
import threading
from collections import Counter
from pathlib import Path
from typing import Any

from kaoyan_ai.config import get_settings
from kaoyan_ai.rag.embeddings import PrecomputedEmbeddingIndex
from kaoyan_ai.schemas import RetrievedItem
from kaoyan_ai.utils.jsonl import load_jsonl


class LocalRetriever:
    """Lightweight local RAG retriever backed by JSONL files.

    Items and TF-IDF indexes are cached per collection and invalidated when the
    source file mtime or size changes. This keeps the simple local workflow while
    avoiding repeated full-file reads and vectorizer fitting on every request.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or get_settings().data_dir
        self._lock = threading.RLock()
        self._items_cache: dict[str, tuple[tuple[int, int], list[RetrievedItem]]] = {}
        self._tfidf_cache: dict[
            tuple[str, str],
            tuple[tuple[int, int], list[RetrievedItem], Any, Any],
        ] = {}
        self._embedding_index = PrecomputedEmbeddingIndex()

    def load_items(self, collection: str = "question_bank") -> list[RetrievedItem]:
        path = self.data_dir / f"{collection}.jsonl"
        signature = self._file_signature(path)

        with self._lock:
            cached = self._items_cache.get(collection)
            if cached and cached[0] == signature:
                return cached[1]

        rows = load_jsonl(path)
        items = []
        for row in rows:
            try:
                items.append(RetrievedItem(**self._normalize_row(row)))
            except Exception:
                continue

        with self._lock:
            self._items_cache[collection] = (signature, items)
            stale_keys = [key for key in self._tfidf_cache if key[0] == collection]
            for key in stale_keys:
                self._tfidf_cache.pop(key, None)

        return items

    def retrieve(
        self,
        query: str,
        *,
        collection: str = "question_bank",
        subject: str | None = None,
        k: int | None = None,
    ) -> list[RetrievedItem]:
        settings = get_settings()
        top_k = k or settings.rag_top_k
        items = self.load_items(collection)
        if subject:
            items = [item for item in items if item.subject == subject]
        if not items:
            return []

        try:
            return self._hybrid(query, collection, subject, items, top_k)
        except Exception:
            return self._keyword_overlap(query, items, top_k)

    def _hybrid(
        self,
        query: str,
        collection: str,
        subject: str | None,
        items: list[RetrievedItem],
        k: int,
    ) -> list[RetrievedItem]:
        """Combine char TF-IDF, BM25 and metadata signals.

        Character TF-IDF handles Chinese semantic similarity reasonably well,
        BM25 preserves exact exam terminology, and metadata boosts prevent a
        superficially similar item from another subject outranking a direct hit.
        """

        semantic = self._tfidf_ranked_scores(query, collection, subject, items)
        lexical = self._bm25_scores(query, items)
        neural = self._embedding_index.scores(
            query,
            collection,
            [item.id for item in items],
        )
        query_lower = query.lower()
        ranked: list[tuple[RetrievedItem, float]] = []
        for index, item in enumerate(items):
            metadata_boost = 0.0
            if item.subject and item.subject.lower() in query_lower:
                metadata_boost += 0.12
            metadata_boost += min(
                0.15,
                sum(0.05 for point in item.knowledge_points if point.lower() in query_lower),
            )
            if neural[index] > 0:
                score = (
                    0.38 * semantic[index]
                    + 0.24 * lexical[index]
                    + 0.26 * neural[index]
                    + metadata_boost
                )
            else:
                score = 0.58 * semantic[index] + 0.30 * lexical[index] + metadata_boost
            ranked.append((item, score))
        ranked.sort(key=lambda pair: pair[1], reverse=True)
        return [item for item, score in ranked[:k] if score > 0]

    def _tfidf_ranked_scores(
        self,
        query: str,
        collection: str,
        subject: str | None,
        items: list[RetrievedItem],
    ) -> list[float]:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        path = self.data_dir / f"{collection}.jsonl"
        signature = self._file_signature(path)
        cache_key = (collection, subject or "")

        with self._lock:
            cached = self._tfidf_cache.get(cache_key)
            if cached and cached[0] == signature:
                cached_items, vectorizer, corpus_matrix = cached[1], cached[2], cached[3]
            else:
                cached_items, vectorizer, corpus_matrix = [], None, None
        if vectorizer is None or corpus_matrix is None:
            corpus = [self._item_text(item) for item in items]
            vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(1, 3))
            corpus_matrix = vectorizer.fit_transform(corpus)
            cached_items = items
            with self._lock:
                self._tfidf_cache[cache_key] = (
                    signature,
                    cached_items,
                    vectorizer,
                    corpus_matrix,
                )
        scores = cosine_similarity(vectorizer.transform([query]), corpus_matrix).flatten()
        by_id = {id(item): float(score) for item, score in zip(cached_items, scores)}
        return [by_id.get(id(item), 0.0) for item in items]

    def _bm25_scores(self, query: str, items: list[RetrievedItem]) -> list[float]:
        query_tokens = self._tokens(query)
        documents = [self._tokens(self._item_text(item)) for item in items]
        if not query_tokens or not documents:
            return [0.0] * len(items)
        document_frequency = Counter()
        for tokens in documents:
            document_frequency.update(set(tokens))
        avg_length = sum(len(tokens) for tokens in documents) / max(len(documents), 1)
        raw_scores: list[float] = []
        k1, b = 1.5, 0.75
        for tokens in documents:
            counts = Counter(tokens)
            score = 0.0
            for token in query_tokens:
                frequency = counts[token]
                if not frequency:
                    continue
                df = document_frequency[token]
                idf = math.log(1 + (len(documents) - df + 0.5) / (df + 0.5))
                denominator = frequency + k1 * (
                    1 - b + b * len(tokens) / max(avg_length, 1)
                )
                score += idf * frequency * (k1 + 1) / denominator
            raw_scores.append(score)
        maximum = max(raw_scores, default=0.0)
        return [score / maximum if maximum else 0.0 for score in raw_scores]

    @staticmethod
    def _tokens(text: str) -> list[str]:
        normalized = re.sub(r"\s+", "", text.lower())
        chars = [char for char in normalized if "\u4e00" <= char <= "\u9fff"]
        bigrams = ["".join(chars[index:index + 2]) for index in range(len(chars) - 1)]
        words = re.findall(r"[a-z0-9_+\-]{2,}", text.lower())
        return chars + bigrams + words

    def _tfidf(
        self,
        query: str,
        collection: str,
        subject: str | None,
        items: list[RetrievedItem],
        k: int,
    ) -> list[RetrievedItem]:
        scores = self._tfidf_ranked_scores(query, collection, subject, items)
        ranked = sorted(zip(items, scores), key=lambda pair: pair[1], reverse=True)
        return [item for item, score in ranked[:k] if score > 0]

    def _keyword_overlap(self, query: str, items: list[RetrievedItem], k: int) -> list[RetrievedItem]:
        query_chars = set(query)
        ranked: list[tuple[RetrievedItem, float]] = []
        for item in items:
            text_chars = set(self._item_text(item))
            overlap = len(query_chars & text_chars)
            normalizer = math.sqrt(max(len(text_chars), 1))
            ranked.append((item, overlap / normalizer))
        ranked.sort(key=lambda pair: pair[1], reverse=True)
        return [item for item, score in ranked[:k] if score > 0]

    def _item_text(self, item: RetrievedItem) -> str:
        return " ".join(
            [
                item.title,
                item.content,
                item.subject,
                " ".join(item.knowledge_points),
                " ".join(item.score_points),
            ]
        )

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)
        difficulty = normalized.get("difficulty")
        difficulty_map = {
            "简单": "基础",
            "容易": "基础",
            "普通": "中等",
            "一般": "中等",
            "困难": "较难",
            "难": "较难",
        }
        if difficulty not in {"基础", "中等", "较难"}:
            normalized["difficulty"] = difficulty_map.get(str(difficulty), "中等")
        if not normalized.get("content"):
            normalized["content"] = (
                normalized.get("detailed_explanation")
                or normalized.get("summary")
                or normalized.get("description")
                or normalized.get("title", "")
            )
        if not normalized.get("title"):
            normalized["title"] = (
                normalized.get("name")
                or normalized.get("knowledge_point")
                or normalized.get("id", "")
            )
        return normalized

    def _file_signature(self, path: Path) -> tuple[int, int]:
        if not path.exists():
            return (0, 0)
        stat = path.stat()
        return (stat.st_mtime_ns, stat.st_size)
