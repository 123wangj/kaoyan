from scripts.remap_low_confidence_with_glm import (
    proposal_groups,
    stage_review_queue,
    validate_model_result,
)


def _task() -> dict:
    return {
        "question_id": "q1",
        "subject": "操作系统",
        "chapter": "第3章 内存管理",
        "candidates": [
            {"id": "kp-page", "title": "分页存储管理"},
            {"id": "kp-segment", "title": "分段存储管理"},
        ],
    }


def test_mapping_can_abstain_instead_of_forcing_a_candidate() -> None:
    result = validate_model_result(
        {
            "question_id": "q1",
            "status": "unmatched",
            "knowledge_point_ids": [],
            "confidence": 0.96,
            "missing_concept": "请求分页",
        },
        _task(),
    )
    assert result["status"] == "unmatched"
    assert result["knowledge_point_ids"] == []


def test_mapping_rejects_low_confidence_or_unknown_ids() -> None:
    low = validate_model_result(
        {
            "status": "matched",
            "knowledge_point_ids": ["kp-page"],
            "confidence": 0.7,
            "evidence": "题目考查页号与页内偏移",
        },
        _task(),
    )
    unknown = validate_model_result(
        {
            "status": "matched",
            "knowledge_point_ids": ["kp-invented"],
            "confidence": 0.99,
            "evidence": "模型自行创造的 ID",
        },
        _task(),
    )
    assert low["status"] == "unmatched"
    assert unknown["status"] == "unmatched"


def test_new_point_requires_repeated_unmatched_support() -> None:
    rows = [
        {
            "question_id": f"q{i}",
            "status": "unmatched",
            "subject": "操作系统",
            "chapter": "第3章 内存管理",
            "missing_concept": "请求分页",
            "missing_concept_definition": "按需调入页面。",
        }
        for i in range(5)
    ]
    assert proposal_groups(rows[:4], min_support=5) == []
    proposals = proposal_groups(rows, min_support=5)
    assert len(proposals) == 1
    assert proposals[0]["support_count"] == 5
    assert proposals[0]["status"] == "needs_review"
