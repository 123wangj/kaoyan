from __future__ import annotations

import time

from kaoyan_ai.school_selection import SchoolSelectionRequest
from kaoyan_ai.school_workflow import SchoolSelectionRunStore


def test_school_workflow_persists_progress_and_result(tmp_path, monkeypatch):
    def fake_analysis(payload, learning_profile=None):
        return {
            "school": payload.school,
            "major": payload.major,
            "learning_readiness": learning_profile,
            "evidence": [{"title": "official"}],
            "trend": {"predicted_range": [350, 365]},
            "heat": {"score": 60},
        }

    monkeypatch.setattr(
        "kaoyan_ai.school_workflow.analyze_school_selection",
        fake_analysis,
    )
    store = SchoolSelectionRunStore(tmp_path)
    started = store.start(
        "user-a",
        SchoolSelectionRequest(school="浙江大学", major="计算机"),
        {"total_answered": 20, "accuracy": 70, "progress": 10},
    )
    run = started
    for _ in range(100):
        run = store.get(started["run_id"], "user-a")
        if run and run["status"] == "completed":
            break
        time.sleep(0.01)
    assert run is not None
    assert run["status"] == "completed"
    assert run["progress"] == 100
    assert run["stages"]["profile"]["status"] == "completed"
    assert run["stages"]["research"]["status"] == "completed"
    assert run["result"]["school"] == "浙江大学"
    assert "user_id" not in run
