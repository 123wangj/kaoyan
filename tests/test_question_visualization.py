from fastapi import HTTPException

from kaoyan_ai import api
from kaoyan_ai.question_visualization import (
    build_question_visualization,
    infer_error_focus,
    visualization_capability,
)


def _question(content: str, explanation: str | None = None) -> dict:
    return {
        "id": "q-visual-1",
        "subject": "操作系统",
        "type": "choice",
        "content": content,
        "options": ["A. 3 次", "B. 4 次", "C. 5 次", "D. 6 次"],
        "answer": "B",
        "explanation": explanation
        or "1. 先读取题干给出的访问序列和页框数量。 2. 按照算法规则逐次检查页面是否命中。 3. 未命中时选择应被淘汰的页面。 4. 统计全部缺页次数，因此选择 B。",
        "knowledge_points": ["页面置换算法"],
    }


def test_process_question_gets_deterministic_visualization_spec() -> None:
    question = _question("使用 LRU 页面置换算法处理访问序列时，缺页次数是多少？")

    capability = visualization_capability(question)
    spec = build_question_visualization(question)

    assert capability == {
        "available": True,
        "category": "page_replacement",
        "label": "页面置换过程",
        "template": "memory-grid",
        "mode": "walkthrough",
        "mode_label": "步骤图解",
    }
    assert spec["question_id"] == question["id"]
    assert spec["answer"] == "B"
    assert len(spec["steps"]) >= 2
    assert any(option["correct"] for option in spec["options"])


def test_lru_simulation_replays_every_reference_and_counts_faults() -> None:
    question = _question("有3个页框，采用 LRU 页面置换算法，访问序列为 1,2,3,1,4,5，缺页次数是多少？")
    spec = build_question_visualization(question)
    simulation = spec["simulation"]

    assert spec["mode"] == "simulation"
    assert simulation["kind"] == "page_replacement"
    assert simulation["faults"] == 5
    assert simulation["states"][3]["hit"] is True
    assert simulation["states"][4]["evicted"] == 2
    assert simulation["states"][-1]["frames"] == [1, 4, 5]


def test_wrong_numeric_answer_maps_back_to_first_missing_fault() -> None:
    question = _question("有3个页框，采用 LRU 页面置换算法，访问序列为 1,2,3,1,4,5，缺页次数是多少？")
    question["answer"] = "C"
    spec = build_question_visualization(question)

    focus = infer_error_focus(spec, "B")

    assert focus["confidence"] == "inferred"
    assert focus["step"] == 5
    assert "第 5 次缺页" in focus["reason"]


def test_sorting_simulation_uses_real_intermediate_arrays() -> None:
    question = _question("关键字序列为 5,1,4,2,8，采用冒泡排序后的结果是？")
    question["knowledge_points"] = ["冒泡排序"]
    spec = build_question_visualization(question)

    assert spec["simulation"]["kind"] == "sorting"
    assert spec["simulation"]["states"][1]["values"] == [1, 4, 2, 5, 8]
    assert spec["simulation"]["result"] == [1, 2, 4, 5, 8]


def test_head_node_purpose_uses_structural_pointer_comparison() -> None:
    question = _question(
        "单链表中，增加一个头结点的目的是（ ）。",
        "不带头结点时，空表和首部操作需要修改头指针。增加头结点后，头指针始终稳定。首部插入删除与中间位置使用相同的指针修改规则，因此方便运算实现。",
    )
    question["subject"] = "数据结构"
    question["knowledge_points"] = ["单链表的定义与基本操作"]
    question["answer"] = "C"

    spec = build_question_visualization(question)

    assert spec["mode"] == "simulation"
    assert spec["simulation"]["kind"] == "linked_list_head"
    assert [state["variant"] for state in spec["simulation"]["states"]] == [
        "without_head", "with_head", "uniform_operation"
    ]
    assert "统一" in spec["simulation"]["result"]


def test_concept_only_question_without_real_state_change_has_no_visualization() -> None:
    question = _question(
        "单链表结点的特点是（ ）。",
        "单链表结点包含数据域和后继指针域。不同结点通过指针形成逻辑上的先后关系。结点地址不要求连续，因此选择 D。",
    )
    question["subject"] = "数据结构"
    question["knowledge_points"] = ["双链表"]

    assert visualization_capability(question) is None
    assert build_question_visualization(question) is None


def test_pipeline_simulation_calculates_cycle_and_total_time() -> None:
    question = _question("一条指令分为3段，时间分别是=2ns,=2ns,=1ns，100条指令流水执行需要多久？")
    question["subject"] = "计算机组成原理"
    question["knowledge_points"] = ["指令流水线"]
    spec = build_question_visualization(question)

    assert spec["simulation"]["cycle"] == 2
    assert spec["simulation"]["first_latency"] == 5
    assert spec["simulation"]["total"] == 203
    assert len(spec["simulation"]["rows"]) == 6


def test_subnet_simulation_exposes_binary_boundary_and_invalid_options() -> None:
    question = _question("采用默认子网掩码，下列可以分配给主机的 IP 地址是？")
    question["subject"] = "计算机网络"
    question["knowledge_points"] = ["IP 地址与子网划分"]
    question["options"] = ["A. 192.46.10.0", "B. 110.47.10.0", "C. 127.10.10.17", "D. 211.60.256.21"]
    spec = build_question_visualization(question)
    candidates = spec["simulation"]["candidates"]

    assert candidates[0]["network"] == "192.46.10.0"
    assert candidates[0]["valid"] is False
    assert candidates[1]["bits"] == ["01101110", "00101111", "00001010", "00000000"]
    assert candidates[1]["valid"] is True
    assert candidates[2]["valid"] is False
    assert candidates[3]["valid"] is False


def test_definition_only_or_incomplete_question_is_not_offered() -> None:
    definition = _question("下列关于操作系统的说法正确的是？")
    definition["knowledge_points"] = ["操作系统基本概念"]
    assert visualization_capability(definition) is None
    assert visualization_capability(_question("LRU 页面置换算法的英文全称是什么？", "解析过短。")) is None


def test_walkthrough_keeps_complete_long_explanation_without_ellipsis() -> None:
    long_step = "先根据二叉树遍历规则判断左子树与右子树的访问关系，" * 8
    explanation = f"1. {long_step}。 2. 最后结合选项得到结论。"
    question = _question("二叉树的前序遍历结果应如何判断？", explanation)
    question["knowledge_points"] = ["二叉树遍历"]

    spec = build_question_visualization(question)

    assert spec["mode"] == "walkthrough"
    assert long_step in spec["full_explanation"]
    assert any(long_step in step for step in spec["steps"])
    assert all(not step.endswith("…") for step in spec["steps"])


def test_visualization_endpoint_reads_server_question_only(monkeypatch) -> None:
    server_question = _question("使用 FIFO 页面置换算法处理页面访问序列，缺页次数是多少？")
    server_question["id"] = "server-q"
    monkeypatch.setattr(api, "_find_question_by_id", lambda question_id: server_question if question_id == "server-q" else None)

    result = api.get_question_visualization("server-q", user="alice")

    assert result["question_id"] == "server-q"
    assert result["category"] == "page_replacement"
    assert "user_id" not in result


def test_visualization_endpoint_returns_wrong_answer_replay_focus(monkeypatch) -> None:
    server_question = _question("有3个页框，采用 LRU 页面置换算法，访问序列为 1,2,3,1,4,5，缺页次数是多少？")
    server_question["answer"] = "C"
    monkeypatch.setattr(api, "_find_question_by_id", lambda _question_id: server_question)

    result = api.get_question_visualization("q-visual-1", selected_option="B", user="alice")

    assert result["error_focus"]["step"] == 5
    assert result["error_focus"]["selected_option"] == "B"


def test_visualization_endpoint_rejects_unknown_or_unsuitable_question(monkeypatch) -> None:
    monkeypatch.setattr(api, "_find_question_by_id", lambda _question_id: None)
    try:
        api.get_question_visualization("missing", user="alice")
        raise AssertionError("missing question must be rejected")
    except HTTPException as exc:
        assert exc.status_code == 404


def test_current_bank_has_broad_but_conservative_visual_coverage() -> None:
    questions = api._load_questions_cached()
    selected = [question for question in questions if visualization_capability(question)]
    categories = {
        visualization_capability(question)["category"] for question in selected
    }

    assert len(selected) >= 300
    assert len(categories) >= 15
    assert all(build_question_visualization(question) for question in selected)
    assert sum(build_question_visualization(question)["mode"] == "simulation" for question in selected) >= 15
