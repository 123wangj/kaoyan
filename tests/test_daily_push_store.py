from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from kaoyan_ai.daily_push_store import DailyPushStore


def test_daily_push_is_generated_once_and_reused_for_the_day(tmp_path):
    store = DailyPushStore(tmp_path, wait_seconds=3)
    calls = []

    def generate():
        calls.append(time.time())
        time.sleep(0.08)
        return {"answer": "今天的固定内容", "push_result": {"questions": []}}

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                lambda _: store.get_or_create("student-1", "2026-07-31", generate),
                range(8),
            )
        )

    assert len(calls) == 1
    assert all(payload["answer"] == "今天的固定内容" for payload, _ in results)
    assert sum(not cached for _, cached in results) == 1
    assert sum(cached for _, cached in results) == 7


def test_next_day_replaces_previous_daily_push(tmp_path):
    store = DailyPushStore(tmp_path)
    first, first_cached = store.get_or_create(
        "student-1",
        "2026-07-31",
        lambda: {"answer": "第一天"},
    )
    second, second_cached = store.get_or_create(
        "student-1",
        "2026-08-01",
        lambda: {"answer": "第二天"},
    )

    assert first["answer"] == "第一天"
    assert first_cached is False
    assert second["answer"] == "第二天"
    assert second_cached is False
    assert store.get("student-1", "2026-07-31") is None
    assert store.get("student-1", "2026-08-01") == {"answer": "第二天"}
    assert len(list((tmp_path / "daily_push_cache").glob("*.json"))) == 1


def test_invalidate_forces_same_day_regeneration(tmp_path):
    store = DailyPushStore(tmp_path)
    store.get_or_create("student-1", "2026-08-02", lambda: {"answer": "old"})

    store.invalidate("student-1")
    payload, cached = store.get_or_create(
        "student-1", "2026-08-02", lambda: {"answer": "from exam report"}
    )

    assert cached is False
    assert payload == {"answer": "from exam report"}
