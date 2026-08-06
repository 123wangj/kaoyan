from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


class DailyPushStore:
    """Persist exactly one current daily-push payload per user.

    Files live on the shared data volume so all Gunicorn workers and future
    application restarts see the same result. The next day's successful
    generation atomically replaces the previous day's file.
    """

    def __init__(
        self,
        data_dir: Path,
        *,
        wait_seconds: float = 110.0,
        stale_lock_seconds: float = 180.0,
    ) -> None:
        self.directory = Path(data_dir) / "daily_push_cache"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.wait_seconds = wait_seconds
        self.stale_lock_seconds = stale_lock_seconds

    def get(self, user_id: str, day: str) -> dict[str, Any] | None:
        path = self._path(user_id)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if record.get("user_id") != user_id or record.get("date") != day:
            return None
        payload = record.get("payload")
        if not isinstance(payload, dict):
            return None
        return json.loads(json.dumps(payload, ensure_ascii=False))

    def get_or_create(
        self,
        user_id: str,
        day: str,
        generator: Callable[[], dict[str, Any]],
    ) -> tuple[dict[str, Any], bool]:
        cached = self.get(user_id, day)
        if cached is not None:
            return cached, True

        lock_path = self._lock_path(user_id)
        deadline = time.monotonic() + self.wait_seconds
        owns_lock = False
        while time.monotonic() < deadline:
            cached = self.get(user_id, day)
            if cached is not None:
                return cached, True
            try:
                descriptor = os.open(
                    lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                try:
                    os.write(descriptor, str(time.time()).encode("ascii"))
                finally:
                    os.close(descriptor)
                owns_lock = True
                break
            except FileExistsError:
                try:
                    if time.time() - lock_path.stat().st_mtime > self.stale_lock_seconds:
                        lock_path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                time.sleep(0.15)

        if not owns_lock:
            cached = self.get(user_id, day)
            if cached is not None:
                return cached, True
            raise TimeoutError("等待今日补给生成超时，请稍后重试")

        try:
            # Another worker may have finished between our last read and lock.
            cached = self.get(user_id, day)
            if cached is not None:
                return cached, True
            payload = generator()
            self._write(user_id, day, payload)
            return json.loads(json.dumps(payload, ensure_ascii=False)), False
        finally:
            lock_path.unlink(missing_ok=True)

    def invalidate(self, user_id: str) -> None:
        """Remove a cached payload so newly available learning evidence is used."""
        self._path(user_id).unlink(missing_ok=True)

    def _write(self, user_id: str, day: str, payload: dict[str, Any]) -> None:
        path = self._path(user_id)
        record = {
            "user_id": user_id,
            "date": day,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "payload": payload,
        }
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.directory,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(record, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
                temp_path = Path(handle.name)
            os.replace(temp_path, path)
            temp_path = None
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def _key(self, user_id: str) -> str:
        return hashlib.sha256(user_id.encode("utf-8")).hexdigest()

    def _path(self, user_id: str) -> Path:
        return self.directory / f"{self._key(user_id)}.json"

    def _lock_path(self, user_id: str) -> Path:
        return self.directory / f"{self._key(user_id)}.lock"
