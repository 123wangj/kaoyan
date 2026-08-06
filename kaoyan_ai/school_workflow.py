from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from kaoyan_ai.school_selection import SchoolSelectionRequest, analyze_school_selection


class SchoolSelectionRunStore:
    """Shared-file run store for long school-selection workflows.

    Run files live on the application's persistent data volume, so SSE readers
    handled by another Gunicorn worker can still observe progress and completed
    results.
    """

    def __init__(self, data_dir: Path):
        self.run_dir = Path(data_dir) / "school_selection_runs"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def start(
        self,
        user_id: str,
        payload: SchoolSelectionRequest,
        learning_profile: dict[str, Any],
    ) -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        now = datetime.now().isoformat(timespec="seconds")
        record = {
            "run_id": run_id,
            "user_id": user_id,
            "status": "queued",
            "progress": 2,
            "current_stage": "queued",
            "message": "分析任务已创建",
            "created_at": now,
            "updated_at": now,
            "cancel_requested": False,
            "request": payload.model_dump(),
            "learning_profile_input": learning_profile,
            "partial": {},
            "result": None,
            "error": None,
            "stages": {
                "profile": {"status": "pending", "message": "读取个人学习画像"},
                "research": {"status": "pending", "message": "检索官方与公开信息"},
                "synthesis": {"status": "pending", "message": "生成个性化综合判断"},
            },
        }
        self._write(record)
        threading.Thread(
            target=self._execute,
            args=(run_id,),
            daemon=True,
            name=f"school-run-{run_id[:8]}",
        ).start()
        return self.public(record)

    def get(self, run_id: str, user_id: str) -> dict[str, Any] | None:
        record = self._read(run_id)
        if not record or record.get("user_id") != user_id:
            return None
        return self.public(record)

    def cancel(self, run_id: str, user_id: str) -> dict[str, Any] | None:
        record = self._read(run_id)
        if not record or record.get("user_id") != user_id:
            return None
        if record.get("status") in {"completed", "failed", "cancelled"}:
            return self.public(record)
        record["cancel_requested"] = True
        record["status"] = "cancelled"
        record["message"] = "分析已取消"
        record["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._write(record)
        return self.public(record)

    def retry(self, run_id: str, user_id: str) -> dict[str, Any] | None:
        record = self._read(run_id)
        if not record or record.get("user_id") != user_id:
            return None
        if record.get("status") not in {"failed", "cancelled"}:
            return self.public(record)
        record["status"] = "queued"
        record["progress"] = 2
        record["current_stage"] = "queued"
        record["message"] = "正在重试失败步骤"
        record["cancel_requested"] = False
        record["error"] = None
        record["result"] = None
        for stage in record.get("stages", {}).values():
            stage["status"] = "pending"
        record["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._write(record)
        threading.Thread(
            target=self._execute,
            args=(run_id,),
            daemon=True,
            name=f"school-retry-{run_id[:8]}",
        ).start()
        return self.public(record)

    def public(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in record.items()
            if key not in {"request", "learning_profile_input", "cancel_requested", "user_id"}
        }

    def _execute(self, run_id: str) -> None:
        try:
            record = self._read(run_id)
            if not record:
                return
            profile = record.get("learning_profile_input") or {}
            self._stage(
                run_id,
                "profile",
                "completed",
                progress=22,
                message="个人学习画像已读取",
                partial={
                    "learning_snapshot": {
                        "attempted": profile.get("total_answered", 0),
                        "total_questions": profile.get("total_questions", 0),
                        "accuracy": profile.get("accuracy", 0),
                        "progress": profile.get("progress", 0),
                    }
                },
            )
            if self._cancelled(run_id):
                return
            self._stage(
                run_id,
                "research",
                "running",
                progress=38,
                message="正在检索院校官网、研招网与公开趋势",
            )
            payload = SchoolSelectionRequest.model_validate(record["request"])
            result = analyze_school_selection(payload, learning_profile=profile)
            if self._cancelled(run_id):
                return
            self._stage(
                run_id,
                "research",
                "completed",
                progress=82,
                message=f"已核验 {len(result.get('evidence') or [])} 条公开来源",
                partial={
                    "research": {
                        "trend": result.get("trend"),
                        "heat": result.get("heat"),
                        "evidence_count": len(result.get("evidence") or []),
                    }
                },
            )
            self._stage(
                run_id,
                "synthesis",
                "running",
                progress=92,
                message="正在生成个人适配度与行动建议",
            )
            record = self._read(run_id) or {}
            if record.get("cancel_requested"):
                return
            record["status"] = "completed"
            record["progress"] = 100
            record["current_stage"] = "completed"
            record["message"] = "综合分析已完成"
            record["result"] = result
            record["stages"]["synthesis"]["status"] = "completed"
            record["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._write(record)
        except Exception as exc:
            record = self._read(run_id)
            if not record:
                return
            stage = str(record.get("current_stage") or "research")
            if stage in record.get("stages", {}):
                record["stages"][stage]["status"] = "failed"
            record["status"] = "failed"
            record["message"] = "分析中断，可重试失败步骤"
            record["error"] = str(exc)[:500]
            record["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._write(record)

    def _stage(
        self,
        run_id: str,
        stage: str,
        status: str,
        *,
        progress: int,
        message: str,
        partial: dict[str, Any] | None = None,
    ) -> None:
        record = self._read(run_id)
        if not record or record.get("cancel_requested"):
            return
        record["status"] = "running"
        record["progress"] = progress
        record["current_stage"] = stage
        record["message"] = message
        record["stages"][stage]["status"] = status
        if partial:
            record.setdefault("partial", {}).update(partial)
        record["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._write(record)

    def _cancelled(self, run_id: str) -> bool:
        record = self._read(run_id)
        return not record or bool(record.get("cancel_requested")) or record.get("status") == "cancelled"

    def _path(self, run_id: str) -> Path:
        safe = "".join(char for char in run_id if char.isalnum())[:64]
        return self.run_dir / f"{safe}.json"

    def _read(self, run_id: str) -> dict[str, Any] | None:
        path = self._path(run_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _write(self, record: dict[str, Any]) -> None:
        path = self._path(str(record["run_id"]))
        temp = path.with_suffix(".tmp")
        with self._lock:
            temp.write_text(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            temp.replace(path)
