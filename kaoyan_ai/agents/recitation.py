from __future__ import annotations

from kaoyan_ai.agents.base import AgentBase
from kaoyan_ai.rag import LocalRetriever
from kaoyan_ai.schemas import AgentRequest, AgentResponse, Intent


class RecitationAgent(AgentBase):
    """把计算机考研知识点整理成更容易记忆的带背材料。"""

    def __init__(self, retriever: LocalRetriever | None = None) -> None:
        super().__init__()
        self.retriever = retriever or LocalRetriever()

    def run(self, request: AgentRequest) -> AgentResponse:
        """召回相关知识片段，并生成适合记忆的带背笔记。"""

        retrieval_query = self.contextual_retrieval_query(request)
        retrieved = self.retriever.retrieve(retrieval_query, collection="knowledge_points", k=4)
        context = "\n\n".join(f"[{item.id}] {item.title}\n{item.content}" for item in retrieved)
        system_prompt = self.common_system_prompt(
            "你负责知识点带背，语言要生动、好记，但不能牺牲准确性。",
            task="recitation",
        )
        user_prompt = f"""
用户要带背的内容：
{request.message}

近期对话上下文：
{self.conversation_context(request)}

长期学习偏好：
{request.metadata.get("semantic_memory") or "暂无稳定偏好记录"}

参考知识点：
{context or "暂无本地知识点召回。"}

请输出：
1. 一句话抓核心
2. 形象解释
3. 考研答题版表述
4. 记忆口诀或对比表
5. 3 个自测问题
"""
        answer = self.llm.generate(system_prompt, user_prompt)
        return AgentResponse(
            intent=Intent.RECITATION,
            answer=answer,
            citations=retrieved,
            next_actions=["生成默写卡片", "生成相似选择题", "明日复习提醒"],
        )
