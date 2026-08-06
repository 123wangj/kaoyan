from __future__ import annotations

from kaoyan_ai.school_selection import (
    SchoolSelectionRequest,
    analyze_school_selection,
)
from kaoyan_ai.readiness import build_personal_learning_signals


class OfflineLLM:
    def generate(self, *_args, **_kwargs) -> str:
        return "当前未配置大模型 API，已返回离线占位结果。"


def fake_search(query: str, _limit: int):
    if "招生简章" in query:
        return [
            {
                "title": "浙江大学2026年硕士研究生招生复试办法",
                "href": "https://grs.zju.edu.cn/yjszs/2026/retest",
                "body": "学校公布2026年复试与录取工作办法。",
            },
            {
                "title": "院校信息库",
                "href": "https://yzst.chsi.com.cn/sch/schoolInfo--schId-100.html",
                "body": "招生简章、专业目录与网报公告。",
            },
        ]
    if "复试线" in query:
        return [
            {
                "title": "2025计算机复试线",
                "href": "https://grs.zju.edu.cn/yjszs/2025/score",
                "body": "2025年相关专业复试基本要求为355分。",
            }
        ]
    if "难度" in query:
        return [
            {
                "title": "某机构2026浙江大学计算机考研趋势分析",
                "href": "https://www.eol.cn/kaoyan/2026/prediction",
                "body": "机构回顾往年最低分355分，并提示热度上升。",
            }
        ]
    return [
        {
            "title": "考研经验讨论",
            "href": "https://example.com/topic/zju-cs",
            "body": "公开讨论页面，2026年更新。",
        }
    ]


def test_school_selection_combines_scores_heat_and_sourced_evidence():
    result = analyze_school_selection(
        SchoolSelectionRequest(
            school="浙江大学",
            major="计算机科学与技术",
            historical_scores=[350, 355, 362],
            score_years=[2024, 2025, 2026],
            target_score=375,
        ),
        search_provider=fake_search,
        llm=OfflineLLM(),
    )
    assert result["trend"]["direction"] == "上升"
    assert result["trend"]["predicted_range"]
    assert result["heat"]["score"] > 0
    assert result["risk"]["confidence"] > 0
    assert "仅供参考" in result["summary"]
    assert any(item["source_type"] == "official" for item in result["evidence"])
    assert any(item["source_type"] == "institution" for item in result["evidence"])
    assert "不等同于真实报考人数" in result["methodology"]


def test_school_selection_does_not_invent_prediction_without_scores():
    result = analyze_school_selection(
        SchoolSelectionRequest(school="北京大学", major="计算机"),
        search_provider=lambda *_args: [],
        llm=OfflineLLM(),
    )
    assert result["trend"]["predicted_range"] is None
    assert result["heat"]["level"] == "数据不足"
    assert "不能给出可靠分数区间" in result["summary"]


def test_school_selection_uses_learning_progress_and_accuracy():
    result = analyze_school_selection(
        SchoolSelectionRequest(
            school="浙江大学",
            major="计算机科学与技术",
        ),
        search_provider=lambda *_args: [],
        llm=OfflineLLM(),
        learning_profile={
            "total_questions": 200,
            "total_answered": 40,
            "total_correct": 22,
            "accuracy": 55,
            "subjects": {
                "数据结构": {"attempted": 18, "total": 50, "accuracy": 72, "progress": 36},
                "计算机组成原理": {"attempted": 10, "total": 50, "accuracy": 40, "progress": 20},
                "操作系统": {"attempted": 8, "total": 50, "accuracy": 50, "progress": 16},
                "计算机网络": {"attempted": 4, "total": 50, "accuracy": 50, "progress": 8},
            },
        },
    )
    readiness = result["learning_readiness"]
    assert readiness["available"] is True
    assert readiness["attempted"] == 40
    assert readiness["progress"] == 20
    assert readiness["accuracy"] == 55
    assert "计算机组成原理" in readiness["weak_subjects"]
    assert any("学习画像" in reason or "正确率" in reason for reason in result["risk"]["reasons"])
    assert "个人学习画像" in result["summary"]


def test_personal_signals_cover_trend_repeat_speed_retention_and_plan():
    state = {
        "exam_date": "2026-12-20",
        "answer_records": [
            {
                "question_id": "q1",
                "is_correct": False,
                "difficulty": "hard",
                "spent_seconds": 180,
                "created_at": "2026-07-10T10:00:00",
            },
            {
                "question_id": "q1",
                "is_correct": True,
                "difficulty": "hard",
                "spent_seconds": 90,
                "created_at": "2026-07-25T10:00:00",
            },
            {
                "question_id": "q2",
                "is_correct": True,
                "difficulty": "easy",
                "spent_seconds": 60,
                "created_at": "2026-07-26T10:00:00",
            },
        ],
        "mastery": {
            "栈": {
                "score": 72,
                "mastery_probability": 0.76,
                "stability_days": 30,
                "last_answered_at": "2026-07-25T10:00:00",
            }
        },
        "daily_tasks": {
            "2026-07-25": {
                "tasks": [
                    {"id": "a", "status": "done"},
                    {"id": "b", "status": "todo"},
                ]
            }
        },
    }
    signals = build_personal_learning_signals(
        state,
        [{"id": "q1", "difficulty": "hard"}, {"id": "q2", "difficulty": "easy"}],
    )
    assert signals["difficulty_weighted_accuracy"] > 50
    assert signals["repeat_improvement"] > 0
    assert signals["review_recovery_rate"] == 100
    assert signals["speed_score"] is not None
    assert signals["retention_score"] is not None
    assert signals["plan_completion"] == 50
    assert signals["sample_confidence"] > 0
