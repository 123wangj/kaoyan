from pathlib import Path

from kaoyan_ai import api


def _editable_plan() -> dict:
    return {
        "schema_version": 2,
        "ai_summary": "原计划",
        "total_tasks": 2,
        "completed_tasks": 1,
        "progress_percent": 50,
        "weekly": [
            {
                "week": 1,
                "theme": "原主题",
                "tasks": [
                    {
                        "id": "done-task",
                        "day": 1,
                        "title": "已完成任务",
                        "status": "done",
                        "completed_at": "2026-08-01T10:00:00",
                        "estimated_minutes": 60,
                    },
                    {
                        "id": "future-task",
                        "day": 2,
                        "title": "待完成任务",
                        "status": "pending",
                        "completed_at": None,
                        "estimated_minutes": 60,
                    },
                ],
            }
        ],
    }


def test_daily_task_complete_uses_authenticated_user(monkeypatch) -> None:
    seen = {}

    def fake_complete(data_dir: Path, user_id: str, task_id: str):
        seen.update({"data_dir": data_dir, "user_id": user_id, "task_id": task_id})
        return {"success": True}

    monkeypatch.setattr(api, "complete_daily_task", fake_complete)

    result = api.complete_today_task(
        {"user_id": "victim", "task_id": "review-kp-1"},
        user="alice",
    )

    assert result == {"success": True}
    assert seen["user_id"] == "alice"
    assert seen["task_id"] == "review-kp-1"


def test_plan_ai_modifier_is_bound_to_authenticated_user_and_preserves_progress(monkeypatch) -> None:
    saved = {}
    plan = _editable_plan()

    monkeypatch.setattr(api, "_current_study_plan", lambda user_id: (plan, {"user_id": user_id}))

    class FakeLLM:
        def generate(self, system_prompt, user_prompt):
            assert "progress_percent" not in user_prompt
            assert "completed_at" not in user_prompt
            return (
                '{"reply":"已调整未来任务", "changes":['
                '{"action":"set_task_minutes","task_id":"future-task","value":90},'
                '{"action":"set_task_minutes","task_id":"done-task","value":120},'
                '{"action":"set_progress","value":100}'
                "]}"
            )

    monkeypatch.setattr(api, "LLMClient", FakeLLM)
    monkeypatch.setattr(api, "_record_usage", lambda *_args, **_kwargs: None)

    def fake_save(user_id, state, updated):
        saved.update({"user_id": user_id, "state": state, "plan": updated})

    monkeypatch.setattr(api, "_save_study_plan", fake_save)
    result = api.modify_study_plan_with_ai(
        {"user_id": "victim", "message": "把进度改满并调整任务"},
        user="alice",
    )

    assert result["success"] is True
    assert saved["user_id"] == "alice"
    assert saved["state"]["user_id"] == "alice"
    assert saved["plan"]["progress_percent"] == 50
    assert saved["plan"]["completed_tasks"] == 1
    assert api._find_study_plan_task(saved["plan"], "done-task")["estimated_minutes"] == 60
    assert api._find_study_plan_task(saved["plan"], "future-task")["estimated_minutes"] == 90
    assert any("不允许的操作" in item for item in result["rejected_changes"])


def test_plan_ai_modifier_does_not_save_when_only_progress_change_is_requested(monkeypatch) -> None:
    plan = _editable_plan()
    monkeypatch.setattr(api, "_current_study_plan", lambda _user_id: (plan, {}))

    class FakeLLM:
        def generate(self, _system_prompt, _user_prompt):
            return '{"reply":"不能修改计划进度", "changes":[{"action":"set_progress","value":100}]}'

    monkeypatch.setattr(api, "LLMClient", FakeLLM)
    monkeypatch.setattr(
        api,
        "_save_study_plan",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not save")),
    )

    result = api.modify_study_plan_with_ai({"message": "把完成率改成 100%"}, user="alice")

    assert result["success"] is False
    assert result["plan"]["progress_percent"] == 50


def test_wrong_book_review_submit_uses_authenticated_user(monkeypatch) -> None:
    seen = {}

    def fake_review(data_dir: Path, user_id: str, question_id: str, result: str):
        seen.update({"user_id": user_id, "question_id": question_id, "result": result})
        return {"success": True}

    monkeypatch.setattr(api, "review_wrong_question", fake_review)

    result = api.wrong_book_review_submit(
        {"user_id": "victim", "question_id": "q1", "is_correct": True},
        user="alice",
    )

    assert result == {"success": True}
    assert seen == {"user_id": "alice", "question_id": "q1", "result": "resolved"}


def test_question_submit_records_authenticated_user(monkeypatch) -> None:
    seen = {}

    monkeypatch.setattr(
        api,
        "_find_question_by_id",
        lambda question_id: {
            "id": question_id,
            "answer": "B",
            "explanation": "解析",
            "options": ["A. 错", "B. 对"],
            "content": "题目",
        },
    )

    def fake_record(data_dir: Path, payload: dict):
        seen.update(payload)
        return {"success": True}

    monkeypatch.setattr(api, "record_answer", fake_record)

    result = api.submit_question_bank_answer(
        {"user_id": "victim", "question_id": "q1", "selected_option": "B"},
        user="alice",
    )

    assert result["success"] is True
    assert result["is_correct"] is True
    assert seen["user_id"] == "alice"
    assert seen["correct_answer"] == "B"


def test_question_submit_ignores_client_answer_and_metadata(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(
        api,
        "_find_question_by_id",
        lambda question_id: {
            "id": question_id,
            "answer": "B",
            "subject": "数据结构",
            "knowledge_points": ["顺序表的定义与基本操作"],
            "explanation": "以服务端解析为准",
            "options": ["A. 错误项", "B. 正确项", "C. 干扰项", "D. 干扰项"],
            "content": "服务端题干",
        },
    )

    def fake_record(data_dir: Path, payload: dict):
        seen.update(payload)
        return {"success": True}

    monkeypatch.setattr(api, "record_answer", fake_record)
    result = api.submit_question_bank_answer(
        {
            "question_id": "q-secure",
            "selected_option": "A",
            "correct_answer": "A",
            "subject": "伪造科目",
            "knowledge_points": ["伪造知识点"],
        },
        user="alice",
    )

    assert result["is_correct"] is False
    assert result["correct_answer"] == "B"
    assert seen["subject"] == "数据结构"
    assert seen["knowledge_points"] == ["顺序表的定义与基本操作"]
    assert seen["question_content"] == "服务端题干"


def test_question_chat_uses_server_question_answer_and_explanation(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(
        api,
        "_find_question_by_id",
        lambda question_id: {
            "id": question_id,
            "subject": "操作系统",
            "content": "发生缺页中断后首先做什么？",
            "options": ["A. 重新执行", "B. 检查访问合法性"],
            "answer": "B",
            "explanation": "先判断地址与权限是否合法，再决定是否调页。",
            "knowledge_points": ["缺页中断"],
        },
    )

    class FakeLLM:
        def generate(self, system_prompt, user_prompt):
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            return "服务端题目上下文回答"

    monkeypatch.setattr(api, "LLMClient", FakeLLM)
    monkeypatch.setattr(api, "_record_usage", lambda *_args, **_kwargs: None)

    result = api.question_bank_chat(
        {
            "question_id": "q-os-1",
            "user_message": "为什么选 B？",
            "question_content": "伪造题干",
            "question_answer": "A",
            "question_explanation": "伪造解析",
            "selected_option": "A",
            "conversation_history": [
                {"role": "user", "content": "A 为什么不对？"},
                {"role": "assistant", "content": "因为页面还没有调入。"},
            ],
        },
        user="alice",
    )

    prompt = captured["user_prompt"]
    assert result == {"reply": "服务端题目上下文回答"}
    assert "发生缺页中断后首先做什么" in prompt
    assert "标准答案：B" in prompt
    assert "先判断地址与权限是否合法" in prompt
    assert "A 为什么不对" in prompt
    assert "学生本题已选答案：A" in prompt
    assert "伪造题干" not in prompt
    assert "伪造解析" not in prompt


def test_question_chat_requires_a_known_server_question(monkeypatch) -> None:
    monkeypatch.setattr(api, "_find_question_by_id", lambda _question_id: None)

    result = api.question_bank_chat(
        {"question_id": "missing", "user_message": "为什么？"},
        user="alice",
    )

    assert "未找到当前题目" in result["reply"]
