from __future__ import annotations

from collections import Counter

from kaoyan_ai import api
from kaoyan_ai.cross_subject_relations import enrich_cross_subject_relations
from kaoyan_ai.knowledge_visualization import (
    _process_spec,
    _simulator_spec,
    build_knowledge_visualization,
)


def _point(title: str = "测试知识点", **extra):
    value = {
        "id": "kp-1",
        "title": title,
        "subject": "数据结构",
        "chapter_id": "chapter-1",
        "chapter_title": "测试章节",
        "content": "这是知识点定义。后续内容用于解释。",
        "score_points": ["定义", "性质", "应用"],
        "knowledge_points": [title],
        "tags": [],
    }
    value.update(extra)
    return value


def test_structure_visualization_is_available_for_every_kind_of_point():
    point = _point(related_point_ids=["kp-2"])
    related = _point("相邻概念", id="kp-2")
    result = build_knowledge_visualization(
        point,
        [point, related],
        [],
        {"wrong_questions": []},
        {"knowledge_points": {}},
    )
    assert result["structure"]["definition"] == "这是知识点定义。"
    assert result["structure"]["components"] == ["定义", "性质", "应用"]
    assert result["structure"]["related"][0]["id"] == "kp-2"
    assert len(result["learning_mission"]["goals"]) == 3
    assert result["learning_mission"]["check"]["stem"]


def test_catalog_coverage_matches_product_tiers():
    points = api._load_knowledge_points()
    processes = [point for point in points if _process_spec(point)["available"]]
    simulators = [point for point in points if _simulator_spec(point)["available"]]
    simulator_types = Counter(_simulator_spec(point)["type"] for point in simulators)

    assert len(points) == 320
    assert 100 <= len(processes) <= 150
    assert 30 <= len(simulators) <= 60
    assert set(simulator_types) == {
        "sorting", "page_replacement", "scheduling", "cache",
        "number", "subnet", "pipeline", "stack_queue",
    }


def test_process_steps_teach_state_reasoning_instead_of_only_listing_titles():
    process = _process_spec(_point("处理机调度", knowledge_points=["处理机调度", "FCFS", "SJF"]))
    assert process["available"] is True
    assert all(stage["input"] and stage["output"] for stage in process["stages"])
    assert all(stage["question"] and stage["answer"] for stage in process["stages"])


def test_every_catalog_point_has_a_goal_and_retrieval_check():
    points = api._load_knowledge_points()
    questions = api._load_questions_cached()
    payloads = [
        build_knowledge_visualization(
            point, points, questions, {"wrong_questions": []}, {"knowledge_points": {}}
        )
        for point in points
    ]
    assert all(item["learning_mission"]["goals"] for item in payloads)
    assert all(item["learning_mission"]["check"]["stem"] for item in payloads)


def test_personalization_marks_only_current_users_wrong_questions():
    point = _point()
    questions = [
        {"id": "q-alice", "content": "Alice 错题", "knowledge_points": [point["title"]]},
        {"id": "q-bob", "content": "Bob 错题", "knowledge_points": [point["title"]]},
    ]
    result = build_knowledge_visualization(
        point,
        [point],
        questions,
        {"wrong_questions": [{"question_id": "q-alice", "knowledge_points": [point["title"]]}]},
        {"knowledge_points": {point["title"]: {"progress": 42, "attempted": 1, "total": 2}}},
    )
    flags = {item["id"]: item["is_wrong"] for item in result["personalization"]["questions"]}
    assert flags == {"q-alice": True, "q-bob": False}
    assert result["personalization"]["mastery_score"] == 42


def test_api_uses_authenticated_user_and_never_a_client_user_id(monkeypatch):
    point = _point()
    seen = []
    monkeypatch.setattr(api, "_load_knowledge_points", lambda: [point])
    monkeypatch.setattr(api, "_load_questions_cached", lambda: [])
    monkeypatch.setattr(api, "load_learning_state", lambda _data_dir, user: seen.append(user) or {"wrong_questions": []})
    monkeypatch.setattr(api, "question_completion_progress", lambda *_: {"knowledge_points": {}})

    result = api.kg_point_visualization("kp-1", user="alice")

    assert result["point"]["id"] == "kp-1"
    assert seen == ["alice"]


def test_curated_cross_subject_relations_are_symmetric_and_explained():
    points = [
        {"id": "kp_co_co_memory_03", "title": "Cache 高速缓存", "subject": "计算机组成原理"},
        {"id": "kp_os_os_memory_05", "title": "虚拟内存管理", "subject": "操作系统"},
    ]

    enriched = enrich_cross_subject_relations(points)

    assert enriched[0]["cross_subject_point_ids"] == ["kp_os_os_memory_05"]
    assert enriched[1]["cross_subject_point_ids"] == ["kp_co_co_memory_03"]
    assert "局部性" in enriched[0]["cross_subject_relations"][0]["theme"]
    assert enriched[0]["cross_subject_relations"][0]["explanation"]
