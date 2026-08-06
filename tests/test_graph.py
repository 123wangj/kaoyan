"""测试对话记忆和 graph 编排。"""

from pathlib import Path
import json
import os
import tempfile

from kaoyan_ai.graph import ConversationMemory, KaoyanTutorGraph
from kaoyan_ai.schemas import AgentRequest, Intent


def test_conversation_memory_add_and_retrieve(tmp_path: Path) -> None:
    """对话记忆可以保存和检索对话历史。"""
    from kaoyan_ai.config import get_settings

    settings = get_settings()
    old_data_dir = settings.data_dir
    settings.data_dir = tmp_path

    mem = ConversationMemory(max_turns=3)
    try:
        mem.add_turn("u_test", "你好", "你好！有什么可以帮助你的？")
        mem.add_turn("u_test", "请讲一下页表", "页表是操作系统中...")

        history = mem.get_history("u_test")
        assert len(history) == 4  # 2 轮 × 2 条记录
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "你好"
        assert history[1]["role"] == "assistant"
        assert history[3]["content"].startswith("页表是")
    finally:
        settings.data_dir = old_data_dir


def test_conversation_memory_trims_long_history(tmp_path: Path) -> None:
    """对话历史超过 max_turns 时自动裁剪。"""
    from kaoyan_ai.config import get_settings

    settings = get_settings()
    old_data_dir = settings.data_dir
    settings.data_dir = tmp_path
    mem = ConversationMemory(max_turns=2)
    try:
        for i in range(5):
            mem.add_turn("u_test", f"问题 {i}", f"回答 {i}")

        history = mem.get_history("u_test")
        # max_turns=2, 所以最多保留 4 条记录（2轮 × 2）
        assert len(history) == 4
        assert history[0]["content"] == "问题 3"
    finally:
        settings.data_dir = old_data_dir


def test_conversation_memory_empty_for_new_user(tmp_path: Path) -> None:
    """新用户没有历史记录。"""
    from kaoyan_ai.config import get_settings

    settings = get_settings()
    old_data_dir = settings.data_dir
    settings.data_dir = tmp_path
    mem = ConversationMemory(max_turns=3)
    try:
        history = mem.get_history("nonexistent_user")
        assert history == []
    finally:
        settings.data_dir = old_data_dir


def test_graph_initializes() -> None:
    """Graph 可以正常初始化。"""
    g = KaoyanTutorGraph()
    assert g.memory is not None
    assert g.intent_agent is not None
    assert len(g.agents) > 0
