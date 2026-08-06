from kaoyan_ai.chat_policy import (
    build_strict_system_prompt,
    classify_chat_scope,
    out_of_scope_response,
)
from kaoyan_ai.graph import KaoyanTutorGraph
from kaoyan_ai.schemas import AgentRequest, Intent


def test_scope_allows_408_and_self_designed_exam_topics():
    allowed = [
        "二叉树的线索化怎么判断？",
        "数据库第三范式怎么判断",
        "编译原理里的 FIRST 集怎么求",
        "计算机考研复试机试应该怎么准备 C++",
        "数学一的线性代数如何复习",
    ]
    assert all(classify_chat_scope(message).allowed for message in allowed)


def test_scope_allows_network_application_layer_topics():
    allowed = [
        "cookie的工作原理是什么？",
        "Cookie 和 Session 有什么区别",
        "HTTP持久连接怎么建立",
        "HTTPS 中 TLS 握手的过程",
        "DHCP 和 DNS 分别有什么作用",
        "SMTP、POP3 和 IMAP 有什么区别",
        "Web缓存和代理服务器的工作原理",
    ]
    assert all(classify_chat_scope(message).allowed for message in allowed)


def test_scope_allows_general_computer_requests_and_rejects_unrelated_topics():
    allowed = [
        "用 Python 写一个电商网站",
        "帮我做一个后台管理系统",
        "Docker 部署失败怎么排查",
        "前端调用 API 时出现跨域错误",
    ]
    rejected = [
        "推荐一部周末看的电影",
        "帮我规划一次云南旅游",
        "教我做红烧肉",
    ]
    assert all(classify_chat_scope(message).allowed for message in allowed)
    assert all(not classify_chat_scope(message).allowed for message in rejected)


def test_scope_allows_real_followup_but_not_unrelated_short_message():
    assert classify_chat_scope("为什么第二步要加一？", has_conversation_context=True).allowed
    assert not classify_chat_scope("推荐电影", has_conversation_context=True).allowed


def test_prompt_covers_broader_computer_postgraduate_exam_scope():
    prompt = build_strict_system_prompt()
    assert "不局限于 408" not in prompt
    assert "院校自命题专业课" in prompt
    assert "数据库" in prompt
    assert "机试" in prompt
    assert "软件项目交付" in prompt


def test_prompt_fixes_exam_context_and_enforces_answer_workflow():
    prompt = build_strict_system_prompt()
    assert "默认按中国计算机考研 408 统考口径作答" in prompt
    assert "只有用户明确说明目标院校、自命题科目、复试或机试时" in prompt
    assert "不直接根据用户猜测、参考答案或选择题选项反推答案" in prompt
    assert "即使用户只问『答案是什么』" in prompt
    assert "『解题—验证—输出』" in prompt
    assert "考试题默认使用『考试背景与考点—解题过程—验证—标准答案—易错点』结构" in prompt


def test_graph_refuses_out_of_scope_before_model_call(tmp_path):
    from kaoyan_ai.config import get_settings

    settings = get_settings()
    original_data_dir = settings.data_dir
    settings.data_dir = tmp_path
    try:
        graph = KaoyanTutorGraph()
        response = graph.run(AgentRequest(user_id="scope-test", message="给我推荐一部电影"))
        assert response.intent == Intent.FALLBACK
        assert response.answer == out_of_scope_response()
        assert response.metadata["scope_allowed"] is False
    finally:
        settings.data_dir = original_data_dir


def test_stream_endpoint_refuses_before_llm(tmp_path, monkeypatch):
    import asyncio

    from kaoyan_ai import api
    from kaoyan_ai.config import get_settings

    settings = get_settings()
    original_data_dir = settings.data_dir
    settings.data_dir = tmp_path
    monkeypatch.setattr(api.db_store, "get_chat_history", lambda *args, **kwargs: [])
    monkeypatch.setattr(api.db_store, "insert_chat_message", lambda *args, **kwargs: None)

    async def run_request():
        response = await api.chat_stream(
            AgentRequest(user_id="ignored", message="教我做红烧肉"),
            user="stream-scope-test",
        )
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)

    try:
        body = asyncio.run(run_request())
        assert "这个问题与计算机领域无关" in body
        assert '"type": "chunk"' in body
    finally:
        settings.data_dir = original_data_dir
