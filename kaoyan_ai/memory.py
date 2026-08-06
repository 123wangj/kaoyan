from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from kaoyan_ai.config import get_settings


class SemanticMemory:
    """Small, inspectable long-term memory store.

    Facts are structured and source-attributed instead of storing another copy
    of the full chat. The JSON implementation is also the database fallback.
    """

    def __init__(self, data_dir: Path | None = None, max_facts: int = 80) -> None:
        self.data_dir = data_dir
        self.max_facts = max_facts
        self._lock = threading.RLock()

    @property
    def _dir(self) -> Path:
        return (self.data_dir or get_settings().data_dir) / "agent_memory"

    def _path(self, user_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "_.-" else "_" for c in user_id) or "anonymous"
        return self._dir / f"{safe}.json"

    def load(self, user_id: str) -> list[dict[str, Any]]:
        path = self._path(user_id)
        if not path.exists():
            return []
        with self._lock:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return []
        return list(payload.get("facts") or [])[-self.max_facts :]

    def remember(
        self,
        user_id: str,
        *,
        category: str,
        key: str,
        value: Any,
        source: str,
        confidence: float = 0.8,
    ) -> dict[str, Any]:
        fact = {
            "category": category,
            "key": key,
            "value": value,
            "source": source,
            "confidence": round(max(0.0, min(1.0, confidence)), 3),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        facts = self.load(user_id)
        facts = [
            item
            for item in facts
            if not (item.get("category") == category and item.get("key") == key)
        ]
        facts.append(fact)
        self._save(user_id, facts[-self.max_facts :])
        return fact

    def context(self, user_id: str, limit: int = 12) -> str:
        facts = sorted(
            self.load(user_id),
            key=lambda item: (float(item.get("confidence", 0)), item.get("updated_at", "")),
            reverse=True,
        )[:limit]
        if not facts:
            return ""
        return "\n".join(
            f"- {item.get('category')}/{item.get('key')}: {item.get('value')}"
            f"（置信度 {item.get('confidence')}，来源 {item.get('source')}）"
            for item in facts
        )

    def learn_from_request(self, user_id: str, message: str) -> list[dict[str, Any]]:
        """Extract only high-confidence, explicit preferences and goals."""

        learned: list[dict[str, Any]] = []
        patterns = [
            ("goal", "target_school", r"(?:目标院校|想考|报考)\s*[：:为是]?\s*([\u4e00-\u9fffA-Za-z0-9·]{2,24}(?:大学|学院))"),
            ("goal", "target_major", r"(?:目标专业|报考专业)\s*[：:为是]?\s*([\u4e00-\u9fffA-Za-z0-9]{2,20})"),
            ("preference", "daily_minutes", r"每天(?:能|可以|计划)?(?:学习|复习)?\s*(\d{1,3})\s*(?:分钟|分)"),
            ("preference", "explanation_style", r"(?:喜欢|希望|请用)\s*(类比|公式|简洁|详细|图示)(?:式)?(?:讲解|解释)?"),
        ]
        for category, key, pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                learned.append(
                    self.remember(
                        user_id,
                        category=category,
                        key=key,
                        value=match.group(1),
                        source="explicit_user_message",
                        confidence=0.95,
                    )
                )
        return learned

    def _save(self, user_id: str, facts: list[dict[str, Any]]) -> None:
        path = self._path(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        payload = {"version": 1, "user_id": user_id, "facts": facts}
        with self._lock:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, path)
