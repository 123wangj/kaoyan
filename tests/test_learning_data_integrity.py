import json
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_jsonl(name: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (DATA_DIR / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_active_questions_have_unique_ids_and_canonical_knowledge_points() -> None:
    questions = _load_jsonl("question_bank.jsonl")
    knowledge = _load_jsonl("knowledge_points.jsonl")
    valid_ids = {item["id"] for item in knowledge}
    ids = [item["id"] for item in questions]

    assert len(ids) == len(set(ids))
    assert all(
        item.get("knowledge_point_ids")
        or item.get("knowledge_mapping_status") in {"pending_glm_review", "unmatched"}
        for item in questions
    )
    assert all(
        item.get("knowledge_points")
        or item.get("knowledge_mapping_status") in {"pending_glm_review", "unmatched"}
        for item in questions
    )
    assert all(
        set(item["knowledge_point_ids"]).issubset(valid_ids)
        for item in questions
    )


def test_curriculum_titles_are_unique_and_graph_relations_are_valid() -> None:
    knowledge = _load_jsonl("knowledge_points.jsonl")
    ids = {item["id"] for item in knowledge}
    subject_titles = [(item["subject"], item["title"]) for item in knowledge]

    assert len(subject_titles) == len(set(subject_titles))
    assert all(item.get("chapter_id") and item.get("chapter_title") for item in knowledge)
    for item in knowledge:
        related = (
            item.get("prerequisite_ids", [])
            + item.get("related_point_ids", [])
            + item.get("cross_subject_point_ids", [])
        )
        assert set(related).issubset(ids)
        assert item["id"] not in related


def test_fabricated_rip_summary_is_not_presented_as_a_2019_exam_question() -> None:
    knowledge = _load_jsonl("knowledge_points.jsonl")
    bad_stem = (
        "RIP 路由协议：①距离向量算法；②最大跳数 15；"
        "③每 30 秒广播路由表；④收敛慢，可能路由环路。"
    )

    assert all(
        question.get("stem") != bad_stem
        for item in knowledge
        for question in item.get("exam_questions", [])
    )


def test_non_choice_exam_examples_must_have_a_traceable_question_source() -> None:
    knowledge = _load_jsonl("knowledge_points.jsonl")

    assert all(
        question.get("type") in {"选", "选择题"}
        or question.get("source_question_id")
        for item in knowledge
        for question in item.get("exam_questions", [])
    )
