from pathlib import Path

from kaoyan_ai import profile_assessment
from kaoyan_ai import api


def _questions() -> list[dict]:
    questions = []
    for subject_index, subject in enumerate(profile_assessment.SUBJECTS):
        for index in range(18):
            answer = "AC" if index == 17 else "ABCD"[(subject_index + index) % 4]
            questions.append(
                {
                    "id": f"q-{subject_index}-{index}",
                    "type": "multiple_choice" if len(answer) > 1 else "choice",
                    "subject": subject,
                    "chapter": f"第 {index % 8 + 1} 章",
                    "knowledge_points": [f"{subject}-知识点-{index}"],
                    "difficulty": ("基础", "中等", "困难")[index % 3],
                    "content": f"{subject}诊断题 {index}",
                    "options": ["A. 甲", "B. 乙", "C. 丙", "D. 丁"],
                    "answer": answer,
                    "explanation": "解析",
                }
            )
    return questions


def test_assessment_selects_40_balanced_questions_without_answers(tmp_path: Path) -> None:
    assessment = profile_assessment.create_assessment(tmp_path, "alice", _questions())

    assert assessment["question_count"] == 40
    assert all("answer" not in question for question in assessment["questions"])
    assert {
        subject: sum(question["subject"] == subject for question in assessment["questions"])
        for subject in profile_assessment.SUBJECTS
    } == {subject: 10 for subject in profile_assessment.SUBJECTS}
    for subject in profile_assessment.SUBJECTS:
        chapters = {
            question["chapter"] for question in assessment["questions"]
            if question["subject"] == subject
        }
        assert len(chapters) >= 6


def test_assessment_grades_and_persists_subject_profile(tmp_path: Path) -> None:
    assessment = profile_assessment.create_assessment(tmp_path, "alice", _questions())
    stored = profile_assessment.get_assessment(tmp_path, "alice", assessment["id"])
    answers = {
        question["id"]: question["answer"]
        for question in stored["questions"]
    }

    graded = profile_assessment.grade(stored, answers)
    finished = profile_assessment.finalize(tmp_path, "alice", assessment["id"], graded, 900)
    current_status = profile_assessment.status(tmp_path, "alice")

    assert finished["result"]["accuracy"] == 100.0
    assert finished["result"]["correct_count"] == 40
    assert all(item["total"] == 10 for item in finished["result"]["subjects"].values())
    assert current_status["has_completed"] is True
    assert current_status["latest_result"]["question_count"] == 40


def test_assessment_requires_every_answer(tmp_path: Path) -> None:
    assessment = profile_assessment.create_assessment(tmp_path, "alice", _questions())
    stored = profile_assessment.get_assessment(tmp_path, "alice", assessment["id"])

    try:
        profile_assessment.grade(stored, {})
    except ValueError as exc:
        assert "40 道题未作答" in str(exc)
    else:
        raise AssertionError("missing answers must be rejected")


def test_submit_records_all_assessment_answers_in_shared_learning_stream(monkeypatch, tmp_path: Path) -> None:
    assessment = profile_assessment.create_assessment(tmp_path, "alice", _questions())
    stored = profile_assessment.get_assessment(tmp_path, "alice", assessment["id"])
    answers = {question["id"]: question["answer"] for question in stored["questions"]}
    recorded = []

    monkeypatch.setattr(api.settings, "data_dir", tmp_path)
    monkeypatch.setattr(api, "record_answer", lambda _data_dir, payload: recorded.append(payload) or {"success": True})
    monkeypatch.setattr(api.daily_push_store, "invalidate", lambda user_id: None)
    monkeypatch.setattr(api, "user_profile_summary", lambda user: {"total_answered": len(recorded)})

    result = api.submit_profile_assessment(
        {"assessment_id": assessment["id"], "answers": answers, "duration_seconds": 1200},
        user="alice",
    )

    assert result["success"] is True
    assert result["profile"]["total_answered"] == 40
    assert len(recorded) == 40
    assert all(item["source"] == f"profile_assessment:{assessment['id']}" for item in recorded)
    assert {item["subject"] for item in recorded} == set(profile_assessment.SUBJECTS)
