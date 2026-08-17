import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kaoyan_ai.exam_store import (
    EXAM_DISTRIBUTION,
    SUBJECTS,
    create_exam,
    get_exam,
    list_exams,
    recent_exam_insights,
    submit_exam,
)


def _questions() -> list[dict]:
    result = []
    for subject in SUBJECTS:
        for index in range(20):
            result.append(
                {
                    "id": f"{subject}-{index}",
                    "type": "choice",
                    "content": f"{subject}第 {index} 题",
                    "options": ["A. 甲", "B. 乙", "C. 丙", "D. 丁"],
                    "answer": "A",
                    "explanation": "标准解析",
                    "subject": subject,
                    "knowledge_points": [f"{subject}知识点"],
                }
            )
    return result


def test_exam_is_balanced_private_and_persisted(tmp_path: Path):
    exam = create_exam(tmp_path, "alice", _questions(), 50)
    counts = Counter(question["subject"] for question in exam["questions"])

    assert sorted(counts.values()) == [12, 12, 13, 13]
    assert all("answer" not in question for question in exam["questions"])
    assert list_exams(tmp_path, "alice")[0]["status"] == "in_progress"
    assert list_exams(tmp_path, "bob") == []


def test_40_question_exam_matches_real_408_subject_distribution(tmp_path: Path):
    exam = create_exam(tmp_path, "alice", _questions(), 40)
    subjects = [question["subject"] for question in exam["questions"]]

    assert Counter(subjects) == Counter(EXAM_DISTRIBUTION)
    assert subjects == sorted(subjects, key=SUBJECTS.index)


def test_exam_excludes_multiple_choice_questions(tmp_path: Path):
    questions = _questions()
    questions[0]["answer"] = "AC"
    exam = create_exam(tmp_path, "alice", questions, 40)

    assert questions[0]["id"] not in {question["id"] for question in exam["questions"]}


def test_submit_scores_and_builds_report_without_mutating_learning_state(tmp_path: Path):
    exam = create_exam(tmp_path, "alice", _questions(), 50)
    learning_state = {
        "answer_records": [
            {"knowledge_points": ["数据结构知识点"], "is_correct": False}
        ]
    }
    before = json.dumps(learning_state, ensure_ascii=False, sort_keys=True)
    answers = {question["id"]: "A" for question in exam["questions"][:40]}

    result = submit_exam(tmp_path, "alice", exam["id"], answers, 600, learning_state)

    assert result is not None
    assert result["score"] == 80.0
    assert result["correct_count"] == 40
    assert result["status"] == "submitted"
    assert result["report"]["history_used"] is True
    assert len(result["report"]["subject_performance"]) == 4
    assert len(result["report"]["wrong_details"]) == 10
    assert result["report"]["diagnosis_overview"]["weakest_subject"] in SUBJECTS
    assert "verification" in result["report"]["study_plan"]
    weak = result["report"]["weak_points"][0]
    assert weak["priority"] in {"high", "medium", "watch"}
    assert weak["evidence"]
    assert weak["likely_causes"]
    assert len(weak["action_plan"]) == 3
    assert all("answer" in question and "explanation" in question for question in result["questions"])
    assert json.dumps(learning_state, ensure_ascii=False, sort_keys=True) == before
    assert get_exam(tmp_path, "alice", exam["id"])["score"] == 80.0


def test_recent_exam_insights_are_available_for_seven_days(tmp_path: Path):
    exam = create_exam(tmp_path, "alice", _questions(), 50)
    submit_exam(tmp_path, "alice", exam["id"], {}, 300, {})

    insights = recent_exam_insights(tmp_path, "alice", days=7)

    assert insights is not None
    assert insights["exam_count"] == 1
    assert insights["latest_exam_id"] == exam["id"]
    assert insights["weak_points"]
    assert insights["weak_points"][0]["source_exam_id"] == exam["id"]

    eight_days_later = datetime.now(timezone.utc) + timedelta(days=8)
    assert recent_exam_insights(tmp_path, "alice", days=7, now=eight_days_later) is None
