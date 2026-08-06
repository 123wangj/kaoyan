from datetime import datetime

from kaoyan_ai import learning


def test_memory_review_queue_prioritizes_long_overdue_weak_point():
    state = {
        "mastery": {
            "页式存储": {
                "subject": "操作系统",
                "score": 42,
                "attempts": 4,
                "correct": 1,
                "last_answered_at": "2026-06-01T09:00:00",
            },
            "TCP 拥塞控制": {
                "subject": "计算机网络",
                "score": 92,
                "attempts": 8,
                "correct": 8,
                "last_answered_at": "2026-07-25T09:00:00",
            },
        }
    }

    queue = learning.memory_review_queue(
        state,
        now=datetime(2026, 7, 30, 12, 0, 0),
    )

    assert queue[0]["knowledge_point"] == "页式存储"
    assert queue[0]["is_due"] is True
    assert queue[0]["overdue_days"] > 0
    assert queue[1]["is_due"] is False


def test_question_note_is_bound_to_question_and_can_be_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr(learning.db_store, "load_state", lambda _user_id: None)
    monkeypatch.setattr(learning.db_store, "upsert_question_note", lambda *args: None)
    monkeypatch.setattr(learning.db_store, "delete_question_note", lambda *args: None)
    drawing = {
        "version": 1,
        "strokes": [
            {
                "tool": "pen",
                "color": "#172554",
                "size": 4,
                "points": [{"x": 0.1, "y": 0.2}, {"x": 0.3, "y": 0.4}],
            }
        ],
    }

    learning.save_question_note(tmp_path, "alice", "q-408-1", "先画页表，再算缺页。", drawing)

    saved = learning.get_question_note(tmp_path, "alice", "q-408-1")
    other = learning.get_question_note(tmp_path, "alice", "q-408-2")
    assert saved["text"] == "先画页表，再算缺页。"
    assert saved["drawing"]["strokes"][0]["points"][1]["x"] == 0.3
    assert other["text"] == ""

    learning.delete_question_note(tmp_path, "alice", "q-408-1")
    assert learning.get_question_note(tmp_path, "alice", "q-408-1")["text"] == ""
