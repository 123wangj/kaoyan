from kaoyan_ai.question_quality import (
    question_is_well_formed,
    question_quality_issues,
)


def _choice(**updates):
    question = {
        "type": "choice",
        "content": "下列说法正确的是（ ）。",
        "options": ["A. 甲", "B. 乙", "C. 丙", "D. 丁"],
        "answer": "A",
        "explanation": "甲符合定义。",
    }
    question.update(updates)
    return question


def test_valid_short_question_is_kept():
    assert question_is_well_formed(_choice(content="正确的是（ ）。"))


def test_garbled_pdf_character_is_rejected():
    assert "garbled_text" in question_quality_issues(_choice(content="这是\u4420乱码"))


def test_wrong_option_count_is_rejected():
    assert "invalid_option_count" in question_quality_issues(
        _choice(options=["A. 甲", "B. 乙"])
    )


def test_duplicate_option_labels_are_rejected():
    assert "invalid_option_labels" in question_quality_issues(
        _choice(options=["A. 甲", "A. 乙", "B. 丙", "B. 丁"])
    )


def test_fifth_option_merged_into_fourth_is_rejected():
    assert "invalid_option_count" in question_quality_issues(
        _choice(options=["A. FCFS", "B. SJF", "C. RR", "D. MFQ E. 优先级"])
    )


def test_obviously_truncated_stem_prefix_is_rejected():
    assert "damaged_source" in question_quality_issues(
        _choice(content="为最高优先级。以下算法中平均周转时间为14的是（ ）。")
    )


def test_explicitly_unrecoverable_alignment_is_rejected():
    assert "unrecoverable_alignment" in question_quality_issues(
        _choice(
            quality_status="unrecoverable_alignment",
            quality_reason="缺少计算所需表格",
        )
    )


def test_explanation_admitting_a_damaged_stem_is_rejected():
    assert "damaged_source" in question_quality_issues(
        _choice(explanation="本题题干虽有残缺，只能猜测原题。")
    )


def test_repaired_performance_question_is_kept():
    question = _choice(
        content=(
            "机器 A 执行某程序需要 20s，机器 B 执行该程序需要 16s，"
            "那么，相对来说，下列结论正确的是（ ）。"
        ),
        options=[
            "A. 所有程序在机器 A 上都比在机器 B 上运行速度慢",
            "B. 机器 B 的速度是机器 A 的 1.25 倍",
            "C. 机器 A 的速度是机器 B 的 1.25 倍",
            "D. 机器 A 比机器 B 慢 1.25 倍",
        ],
    )
    assert question_is_well_formed(question)
