from __future__ import annotations

import json
import math
import threading
from pathlib import Path
from typing import Any

from kaoyan_ai.config import get_settings


class PrecomputedEmbeddingIndex:
    """Optional neural embedding channel with an explicit offline index.

    Retrieval never embeds the full corpus during a user request. A separate
    build script creates the index; online requests only embed the query.
    """

    def __init__(self, index_dir: Path | None = None) -> None:
        self.index_dir = index_dir or get_settings().rag_embedding_index_dir
        self._cache: dict[str, tuple[tuple[int, int], dict[str, list[float]]]] = {}
        self._lock = threading.RLock()

    def available(self, collection: str) -> bool:
        return self._path(collection).exists()

    def scores(self, query: str, collection: str, item_ids: list[str]) -> list[float]:
        settings = get_settings()
        if not settings.rag_enable_embeddings or not settings.openai_api_key:
            return [0.0] * len(item_ids)
        vectors = self._load(collection)
        if not vectors:
            return [0.0] * len(item_ids)
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                timeout=settings.llm_timeout_seconds,
            )
            response = client.embeddings.create(
                model=settings.embedding_model,
                input=[query],
            )
            query_vector = list(response.data[0].embedding)
        except Exception:
            return [0.0] * len(item_ids)
        raw = [self._cosine(query_vector, vectors.get(item_id, [])) for item_id in item_ids]
        maximum = max(raw, default=0.0)
        return [value / maximum if maximum > 0 else 0.0 for value in raw]

    def _load(self, collection: str) -> dict[str, list[float]]:
        path = self._path(collection)
        if not path.exists():
            return {}
        stat = path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            cached = self._cache.get(collection)
            if cached and cached[0] == signature:
                return cached[1]
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                vectors = {
                    str(item["id"]): [float(value) for value in item["embedding"]]
                    for item in payload.get("items", [])
                    if item.get("id") and item.get("embedding")
                }
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                return {}
            self._cache[collection] = (signature, vectors)
            return vectors

    def _path(self, collection: str) -> Path:
        return self.index_dir / f"{collection}.json"

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if not left or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        norm_left = math.sqrt(sum(value * value for value in left))
        norm_right = math.sqrt(sum(value * value for value in right))
        return dot / max(norm_left * norm_right, 1e-12)
