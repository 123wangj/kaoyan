from __future__ import annotations

from kaoyan_ai import api
from kaoyan_ai.agents.solution import SolutionAgent
from kaoyan_ai.schemas import AgentRequest, AgentResponse, Intent


class _CaptureRetriever:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def retrieve(self, query: str, **_kwargs):
        self.queries.append(query)
        return []


class _CaptureLLM:
    def __init__(self) -> None:
        self.user_prompt = ""

    def generate(self, _system_prompt, user_prompt, _image_base64=None):
        self.user_prompt = user_prompt
        return "已结合上一轮说明原因。"


def test_solution_followup_uses_history_in_rag_and_model_prompt():
    retriever = _CaptureRetriever()
    llm = _CaptureLLM()
    agent = SolutionAgent(retriever=retriever)
    agent.llm = llm
    request = AgentRequest(
        user_id="followup-user",
        message="为什么第三步要加一？",
        metadata={
            "conversation_history": (
                "用户: 请讲解虚拟地址转换这道题\n"
                "AI: 第三步需要计算跨越的页边界数量。"
            )
        },
    )

    response = agent.run(request)

    assert response.intent == Intent.SOLVE_QUESTION
    assert all("请讲解虚拟地址转换这道题" in query for query in retriever.queries)
    assert "第三步需要计算跨越的页边界数量" in llm.user_prompt
    assert "为什么第三步要加一" in llm.user_prompt


def test_chat_json_endpoint_loads_durable_history(monkeypatch):
    captured: dict[str, AgentRequest] = {}

    monkeypatch.setattr(api, "_check_rate_limit", lambda _user_id: True)
    monkeypatch.setattr(api, "_record_usage", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        api.db_store,
        "get_chat_history",
        lambda *_args, **_kwargs: [
            {"role": "user", "content": "什么是缺页中断？"},
            {"role": "assistant", "content": "它发生在访问页不在内存时。"},
        ],
    )
    monkeypatch.setattr(api.db_store, "insert_chat_message", lambda *_args, **_kwargs: None)

    def fake_run(request: AgentRequest) -> AgentResponse:
        captured["request"] = request
        return AgentResponse(intent=Intent.SOLVE_QUESTION, answer="追问回答")

    monkeypatch.setattr(api.graph, "run", fake_run)

    api.chat(AgentRequest(message="那之后会发生什么？"), user="followup-user")

    history = captured["request"].metadata["conversation_history"]
    assert "什么是缺页中断" in history
    assert "访问页不在内存" in history


def test_history_formatter_keeps_longer_answer_context():
    explanation = "页表项解释。" * 80
    history = api._format_conversation_history(
        [
            {"role": "user", "content": "解释这道地址转换题"},
            {"role": "assistant", "content": explanation},
        ]
    )

    assert "解释这道地址转换题" in history
    assert len(history) > 200
    assert explanation[:500] in history
