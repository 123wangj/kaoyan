import json
from pathlib import Path
from types import SimpleNamespace

from kaoyan_ai import learning
from kaoyan_ai import api
from kaoyan_ai.agents import daily_push
from kaoyan_ai.schemas import UserProfile


def _disable_postgres(monkeypatch) -> None:
    monkeypatch.setattr(learning.db_store, "load_state", lambda user_id: None)
    monkeypatch.setattr(learning.db_store, "insert_answer_record", lambda **kwargs: None)
    monkeypatch.setattr(learning.db_store, "update_kp_mastery", lambda *args, **kwargs: None)
    monkeypatch.setattr(learning.db_store, "upsert_wrong_question", lambda **kwargs: None)
    monkeypatch.setattr(
        learning.db_store, "get_daily_task_completions", lambda *args, **kwargs: {}
    )


def test_record_answer_creates_user_directory_and_updates_daily_tasks(
    tmp_path: Path, monkeypatch
) -> None:
    _disable_postgres(monkeypatch)
    result = learning.record_answer(
        tmp_path,
        {
            "user_id": "new-user",
            "question_id": "q1",
            "subject": "数据结构",
            "knowledge_points": ["顺序表的定义与基本操作"],
            "selected_option": "A",
            "correct_answer": "B",
        },
    )

    assert result["is_correct"] is False
    state_path = tmp_path / "users" / "new-user.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["mastery"]["顺序表的定义与基本操作"]["score"] == 37

    tasks = learning.today_tasks(tmp_path, "new-user", "2026-07-29")["tasks"]
    review = next(task for task in tasks if task.get("knowledge_point") == "顺序表的定义与基本操作")
    assert review["mastery_score"] == 37
    assert any(task.get("question_id") == "q1" for task in tasks)


def test_profile_accuracy_uses_latest_attempt_per_question(
    tmp_path: Path, monkeypatch
) -> None:
    _disable_postgres(monkeypatch)
    state = {
        "user_id": "alice",
        "answer_records": [
            {"question_id": "q1", "subject": "操作系统", "is_correct": False},
            {"question_id": "q1", "subject": "操作系统", "is_correct": True},
            {"question_id": "q2", "subject": "操作系统", "is_correct": False},
        ],
    }
    learning.save_learning_state(tmp_path, "alice", state)
    profile = learning.user_profile_payload(
        tmp_path,
        "alice",
        {"total_tokens": 0, "total_requests": 0},
    )
    assert profile["answer_stats"]["total_questions"] == 2
    assert profile["answer_stats"]["correct_count"] == 1
    assert profile["answer_stats"]["accuracy"] == 50.0


def test_postgres_mastery_is_authoritative_when_available(
    tmp_path: Path, monkeypatch
) -> None:
    learning.save_learning_state(
        tmp_path,
        "alice",
        {
            "user_id": "alice",
            "mastery": {
                "顺序表的定义与特点": {
                    "subject": "数据结构",
                    "score": 65,
                    "attempts": 1,
                    "correct": 1,
                    "wrong": 0,
                }
            },
        },
    )
    monkeypatch.setattr(
        learning.db_store,
        "load_state",
        lambda user_id: {
            "user_id": user_id,
            "answer_records": [],
            "wrong_questions": [],
            "mastery": {
                "线性表": {
                    "subject": "数据结构",
                    "score": 65,
                    "attempts": 1,
                    "correct": 1,
                    "wrong": 0,
                }
            },
        },
    )
    state = learning.load_learning_state(tmp_path, "alice")
    assert set(state["mastery"]) == {"线性表"}


def test_daily_push_fallback_uses_complete_local_questions(
    tmp_path: Path, monkeypatch
) -> None:
    row = {
        "id": "q-local",
        "type": "choice",
        "subject": "计算机网络",
        "content": "TCP 建立连接需要几次握手？",
        "options": ["A. 一次", "B. 两次", "C. 三次", "D. 四次"],
        "answer": "C",
        "explanation": "TCP 使用三次握手建立连接。",
        "knowledge_points": ["TCP 三次握手"],
    }
    (tmp_path / "question_bank.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        daily_push,
        "get_settings",
        lambda: SimpleNamespace(data_dir=tmp_path),
    )

    questions = daily_push.DailyPushAgent()._fallback_questions(
        "计算机网络", "TCP 三次握手"
    )
    assert len(questions) == 1
    assert questions[0].answer == "C"
    assert len(questions[0].options) == 4
    assert questions[0].explanation


def test_daily_push_does_not_force_same_subject_question(
    tmp_path: Path, monkeypatch
) -> None:
    row = {
        "id": "q-other",
        "type": "choice",
        "subject": "计算机网络",
        "content": "IP 协议位于哪一层？",
        "options": ["A. 应用层", "B. 传输层", "C. 网络层", "D. 链路层"],
        "answer": "C",
        "explanation": "IP 属于网络层。",
        "knowledge_points": ["IP 协议"],
    }
    (tmp_path / "question_bank.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        daily_push,
        "get_settings",
        lambda: SimpleNamespace(data_dir=tmp_path),
    )
    assert (
        daily_push.DailyPushAgent()._fallback_questions(
            "计算机网络", "TCP 三次握手"
        )
        == []
    )


def test_daily_push_prioritizes_recent_exam_weak_point(monkeypatch) -> None:
    agent = daily_push.DailyPushAgent(
        exam_insights={
            "weak_points": [
                {
                    "name": "Page replacement",
                    "subject": "Operating Systems",
                    "evidence": "3 of 4 questions were wrong",
                    "action_plan": ["Compare FIFO, LRU and OPT"],
                }
            ]
        }
    )
    monkeypatch.setattr(agent, "_lookup_knowledge_content", lambda *args: "base content")
    monkeypatch.setattr(agent, "_expand_knowledge_content", lambda subject, title, content: content)
    monkeypatch.setattr(agent, "_generate_questions_with_llm", lambda **kwargs: [])

    result = agent._generate_daily_push(UserProfile(user_id="alice"))

    assert result.knowledge_point_title == "Page replacement"
    assert result.subject == "Operating Systems"
    assert "3 of 4" in result.knowledge_point_content
    assert "FIFO" in result.knowledge_point_content


def test_local_study_plan_prioritizes_real_weak_point() -> None:
    summary, weekly = api._build_local_study_plan(
        answers={"focus": "四科均衡", "daily_min": "60-120 分钟"},
        weak_points=[
            {"subject": "操作系统", "knowledge_point": "页面置换算法", "score": 37}
        ],
        weak_subjects=["操作系统"],
        open_wrong_count=4,
    )
    assert "操作系统" in summary
    assert len(weekly) == 4
    assert "页面置换算法" in " ".join(weekly[0]["daily_tasks"])
    assert "测验" in " ".join(weekly[1]["daily_tasks"])


def test_study_plan_duration_uses_exact_user_selection() -> None:
    for months in range(1, 13):
        assert api._study_plan_week_count(f"{months}个月") == months * 4
    assert api._study_plan_week_count("6个月以上") == 28
    assert api._study_plan_week_count("4-6个月") == 20


def test_study_plan_personalization_uses_goal_weakness_and_extra() -> None:
    personalized = api._study_plan_personalization(
        {
            "goal": "冲 130+ 分",
            "weak": "做题速度",
            "extra": "每周 6 天，每天 100 分钟，重点加强操作系统，多做题",
        }
    )

    assert personalized["question_factor"] > 1.5
    assert personalized["overrides"] == {
        "study_days_per_week": 6,
        "daily_minutes": 100,
        "focus": "操作系统",
    }
    assert personalized["extra"].startswith("每周 6 天")


def test_memory_review_items_receive_trusted_knowledge_point_ids(monkeypatch) -> None:
    monkeypatch.setattr(
        api,
        "_load_knowledge_points",
        lambda: [
            {
                "id": "os-kp-1",
                "subject": "操作系统",
                "title": "进程同步与互斥",
                "chapter_id": "os-2",
                "chapter_title": "进程管理",
            }
        ],
    )

    result = api._hydrate_memory_review_points(
        [{"subject": "操作系统", "knowledge_point": "进程同步与互斥"}]
    )

    assert result[0]["knowledge_point_id"] == "os-kp-1"
    assert result[0]["chapter_id"] == "os-2"


def test_plan_question_selection_is_round_robin() -> None:
    pools = [
        [{"id": "a1"}, {"id": "a2"}, {"id": "a3"}],
        [{"id": "b1"}, {"id": "b2"}, {"id": "b3"}],
    ]
    result = api._take_balanced_questions(pools, 4, set())
    assert [item["id"] for item in result] == ["a1", "b1", "a2", "b2"]


def test_unlabeled_knowledge_is_removed_from_mastery_and_tasks() -> None:
    state = {
        "user_id": "alice",
        "answer_records": [{"question_id": "q1", "subject": "数据结构", "is_correct": False}],
        "mastery": {
            "未标注知识点": {"subject": "数据结构", "score": 1, "attempts": 3},
            "线性表": {"subject": "数据结构", "score": 45, "attempts": 2},
        },
    }
    normalized = learning._normalize_state(state, "alice")
    assert [item["knowledge_point"] for item in learning.mastery_summary(normalized)] == ["线性表"]
    titles = [task["title"] for task in learning._build_daily_tasks(normalized, "2026-07-30")]
    assert all("未标注" not in title for title in titles)


def test_subject_progress_uses_completed_questions_over_subject_total(
    tmp_path: Path, monkeypatch
) -> None:
    _disable_postgres(monkeypatch)
    learning.save_learning_state(
        tmp_path,
        "alice",
        {
            "user_id": "alice",
            "answer_records": [
                {"question_id": "q1", "subject": "操作系统", "is_correct": True},
            ],
            "mastery": {
                "线性表": {
                    "subject": "数据结构",
                    "score": 65,
                    "attempts": 2,
                    "correct": 1,
                    "wrong": 1,
                },
            },
        },
    )
    profile = learning.user_profile_payload(
        tmp_path,
        "alice",
        {"total_tokens": 0, "total_requests": 0},
        questions=[
            {"id": "q1", "subject": "操作系统"},
            {"id": "q2", "subject": "操作系统"},
            {"id": "q3", "subject": "操作系统"},
            {"id": "q4", "subject": "数据结构"},
        ],
    )
    assert profile["subject_mastery"]["数据结构"]["score"] == 0
    assert profile["subject_mastery"]["操作系统"]["score"] == 33.3
    assert profile["subject_mastery"]["操作系统"]["answer_count"] == 1
    assert profile["subject_mastery"]["操作系统"]["question_count"] == 3
    assert profile["subject_mastery"]["计算机网络"]["score"] == 0


def test_personal_profile_counts_only_unique_questions_in_current_catalog(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state = {
        "version": 1,
        "user_id": "alice",
        "answer_records": [
            {"question_id": "q1", "subject": "数据结构", "is_correct": False},
            {"question_id": "q1", "subject": "数据结构", "is_correct": True},
            {"question_id": "retired", "subject": "操作系统", "is_correct": True},
            {"question_id": "", "subject": "计算机网络", "is_correct": True},
        ],
        "wrong_questions": [],
        "wrong_book": {},
        "mastery": {},
        "daily_tasks": {},
    }
    monkeypatch.setattr("kaoyan_ai.learning.load_learning_state", lambda *_: state)

    profile = learning.user_profile_payload(
        tmp_path,
        "alice",
        {"total_tokens": 0, "total_requests": 0},
        questions=[{"id": "q1", "subject": "数据结构"}],
        knowledge_points=[],
    )

    assert profile["answer_stats"]["total_questions"] == 1
    assert profile["answer_stats"]["correct_count"] == 1
    assert profile["answer_stats"]["accuracy"] == 100.0


def test_personal_profile_and_question_overview_share_completion_totals(
    monkeypatch,
) -> None:
    state = {
        "user_id": "alice",
        "answer_records": [
            {"question_id": "q1", "subject": "数据结构", "is_correct": True},
            {"question_id": "q2", "subject": "操作系统", "is_correct": False},
            {"question_id": "retired", "subject": "计算机网络", "is_correct": True},
        ],
        "wrong_questions": [],
        "wrong_book": {},
        "mastery": {},
        "daily_tasks": {},
    }
    questions = [
        {"id": "q1", "subject": "数据结构"},
        {"id": "q2", "subject": "操作系统"},
    ]
    monkeypatch.setattr(api, "load_learning_state", lambda *_: state)
    monkeypatch.setattr(learning, "load_learning_state", lambda *_: state)
    monkeypatch.setattr(api, "_load_questions_cached", lambda: questions)
    monkeypatch.setattr(api, "_load_knowledge_points", lambda: [])

    overview = api.user_stats_overview(user="alice")
    profile = api.user_profile(user="alice")

    assert profile["answer_stats"]["total_questions"] == overview["total_answered"] == 2
    assert profile["answer_stats"]["correct_count"] == overview["total_correct"] == 1
    assert profile["answer_stats"]["accuracy"] == overview["accuracy"] == 50.0


def test_new_user_state_does_not_inherit_sample_answers(tmp_path: Path) -> None:
    (tmp_path / "sample_user_profile.json").write_text(
        json.dumps(
            {
                "answer_records": [
                    {"question_id": "demo-q", "subject": "操作系统", "is_correct": True}
                ],
                "wrong_questions": [{"question_id": "demo-q", "subject": "操作系统"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    state = learning._seed_from_sample_profile(tmp_path, "brand-new-user")

    assert state["answer_records"] == []
    assert state["wrong_questions"] == []
    assert state["wrong_book"] == {}


def test_wrong_review_task_uses_complete_question_stem() -> None:
    stem = "若采用邻接矩阵存储图，下列关于空间复杂度的说法正确的是（ ）。"
    state = learning._normalize_state(
        {
            "user_id": "alice",
            "answer_records": [
                {"question_id": "q1", "subject": "数据结构", "is_correct": False}
            ],
            "wrong_book": {
                "q1": {
                    "question_id": "q1",
                    "subject": "数据结构",
                    "knowledge_points": ["图的存储"],
                    "content": stem,
                    "status": "open",
                }
            },
        },
        "alice",
    )
    tasks = learning._build_daily_tasks(state, "2026-07-30")
    wrong_task = next(task for task in tasks if task["type"] == "wrong_review")
    assert wrong_task["title"] == f"复盘错题：{stem}"
    assert "q1" not in wrong_task["title"]


def test_stats_overview_returns_question_completion_progress(monkeypatch) -> None:
    monkeypatch.setattr(
        api,
        "load_learning_state",
        lambda *args, **kwargs: {
            "answer_records": [
                {"question_id": "q1", "subject": "数据结构", "is_correct": True}
            ],
            "mastery": {
                "线性表": {
                    "subject": "数据结构",
                    "score": 65,
                    "attempts": 2,
                    "correct": 1,
                    "wrong": 1,
                }
            },
        },
    )
    monkeypatch.setattr(
        api,
        "_load_questions_cached",
        lambda *args, **kwargs: [
            {"id": "q1", "subject": "数据结构"},
            {"id": "q2", "subject": "数据结构"},
            {"id": "q3", "subject": "数据结构"},
            {"id": "q4", "subject": "数据结构"},
        ],
    )
    result = api.user_stats_overview(user="alice")
    assert result["by_subject_backend"]["数据结构"]["mastery_score"] == 25
    assert result["by_subject_backend"]["数据结构"]["attempted"] == 1
    assert result["by_subject_backend"]["数据结构"]["total"] == 4
    assert result["by_subject_backend"]["数据结构"]["mastery_source"] == "question_completion"
    assert result["by_subject_backend"]["计算机网络"]["mastery_score"] == 0
    assert result["total_answered"] == sum(
        item["attempted"] for item in result["by_subject_backend"].values()
    )
    assert result["total_correct"] == sum(
        item["correct"] for item in result["by_subject_backend"].values()
    )


def test_stats_overview_excludes_records_outside_current_question_bank(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        api,
        "load_learning_state",
        lambda *args, **kwargs: {
            "answer_records": [
                {"question_id": "q1", "subject": "数据结构", "is_correct": True},
                {"question_id": "retired", "subject": "操作系统", "is_correct": True},
                {"question_id": "", "subject": "计算机网络", "is_correct": False},
            ]
        },
    )
    monkeypatch.setattr(
        api,
        "_load_questions_cached",
        lambda *args, **kwargs: [
            {"id": "q1", "subject": "数据结构"},
            {"id": "q2", "subject": "操作系统"},
        ],
    )

    result = api.user_stats_overview(user="alice")

    assert result["total_answered"] == 1
    assert result["total_correct"] == 1
    assert result["accuracy"] == 100
    assert sum(
        item["attempted"] for item in result["by_subject_backend"].values()
    ) == result["total_answered"]


def test_question_completion_progress_maps_chapter_by_knowledge_point_id() -> None:
    state = {
        "answer_records": [
            {"question_id": "q1", "subject": "数据结构", "is_correct": False},
        ]
    }
    questions = [
        {
            "id": "q1",
            "subject": "数据结构",
            "knowledge_point_ids": ["kp-list"],
        },
        {
            "id": "q2",
            "subject": "数据结构",
            "knowledge_point_ids": ["kp-list"],
        },
        {
            "id": "q3",
            "subject": "数据结构",
            "knowledge_point_ids": ["kp-tree"],
        },
    ]
    knowledge = [
        {
            "id": "kp-list",
            "title": "线性表",
            "subject": "数据结构",
            "chapter_id": "ds-list",
            "chapter_title": "线性表",
        },
        {
            "id": "kp-tree",
            "title": "树",
            "subject": "数据结构",
            "chapter_id": "ds-tree",
            "chapter_title": "树与二叉树",
        },
    ]
    progress = learning.question_completion_progress(state, questions, knowledge)
    assert progress["subjects"]["数据结构"]["progress"] == 33.3
    assert progress["chapters"]["数据结构||ds-list"]["progress"] == 50
    assert progress["chapters"]["数据结构||ds-tree"]["progress"] == 0
    mastery = learning.completion_mastery_summary(state, questions, knowledge)
    line_list = next(item for item in mastery if item["knowledge_point"] == "线性表")
    assert line_list["score"] == 50
    assert line_list["attempts"] == 1
    assert line_list["total_questions"] == 2
    assert line_list["accuracy"] == 0
    assert line_list["knowledge_point_id"] == "kp-list"
    assert line_list["chapter_id"] == "ds-list"
    assert line_list["chapter_title"] == "线性表"


def test_today_tasks_do_not_change_when_answers_change_same_day(
    tmp_path: Path, monkeypatch
) -> None:
    _disable_postgres(monkeypatch)
    learning.save_learning_state(
        tmp_path,
        "alice",
        {
            "user_id": "alice",
            "answer_records": [
                {
                    "question_id": "q1",
                    "subject": "数据结构",
                    "knowledge_points": ["线性表"],
                    "is_correct": False,
                }
            ],
            "mastery": {
                "线性表": {
                    "subject": "数据结构",
                    "score": 37,
                    "attempts": 1,
                    "correct": 0,
                    "wrong": 1,
                }
            },
        },
    )
    first = learning.today_tasks(tmp_path, "alice", "2026-07-30")
    state = learning.load_learning_state(tmp_path, "alice")
    state["answer_records"].append(
        {
            "question_id": "q2",
            "subject": "操作系统",
            "knowledge_points": ["死锁"],
            "is_correct": False,
        }
    )
    state["mastery"]["死锁"] = {
        "subject": "操作系统",
        "score": 5,
        "attempts": 1,
        "correct": 0,
        "wrong": 1,
    }
    learning.save_learning_state(tmp_path, "alice", state)
    refreshed = learning.today_tasks(tmp_path, "alice", "2026-07-30")
    assert [task["id"] for task in refreshed["tasks"]] == [
        task["id"] for task in first["tasks"]
    ]


def test_today_tasks_prioritize_recent_exam_report_and_refresh_cache(
    tmp_path: Path, monkeypatch
) -> None:
    _disable_postgres(monkeypatch)
    learning.save_learning_state(tmp_path, "alice", {"user_id": "alice"})
    first = learning.today_tasks(tmp_path, "alice", "2026-08-02")
    first["tasks"][0]["status"] = "done"
    learning.save_learning_state(
        tmp_path,
        "alice",
        {
            **learning.load_learning_state(tmp_path, "alice"),
            "daily_tasks": {"2026-08-02": first},
        },
    )
    exam_context = {
        "latest_exam_id": "exam-1",
        "latest_submitted_at": "2026-08-02T10:00:00+08:00",
        "weak_points": [
            {
                "name": "TCP congestion control",
                "subject": "Computer Networks",
                "priority": "high",
                "priority_label": "High",
                "combined_error_rate": 80,
                "evidence": "2 of 2 exam questions were wrong",
                "likely_causes": ["Confused congestion window updates"],
                "action_plan": ["Draw the state transition diagram"],
                "wrong_question_ids": ["q1", "q2"],
                "source_exam_id": "exam-1",
            }
        ],
    }

    refreshed = learning.today_tasks(
        tmp_path, "alice", "2026-08-02", exam_context=exam_context
    )

    report_task = refreshed["tasks"][0]
    assert report_task["source"] == "recent_exam_report"
    assert report_task["knowledge_point"] == "TCP congestion control"
    assert report_task["source_exam_id"] == "exam-1"
    assert "2 of 2" in report_task["description"]
    mixed = refreshed["tasks"][-1]
    assert mixed["source"] == "recent_exam_report"
    assert mixed["knowledge_points"] == ["TCP congestion control"]
