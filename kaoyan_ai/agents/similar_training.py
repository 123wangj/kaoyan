from __future__ import annotations

from kaoyan_ai.agents.base import AgentBase
from kaoyan_ai.rag import LocalRetriever
from kaoyan_ai.schemas import AgentRequest, AgentResponse, Intent


class SimilarTrainingAgent(AgentBase):
    """生成与计算机考研难度对齐的相似题训练。"""

    def __init__(self, retriever: LocalRetriever | None = None) -> None:
        super().__init__()
        self.retriever = retriever or LocalRetriever()

    def run(self, request: AgentRequest) -> AgentResponse:
        """以召回题目为锚点，让模型生成同类训练题。"""

        retrieval_query = self.contextual_retrieval_query(request)
        retrieved = self.retriever.retrieve(retrieval_query, collection="question_bank", k=6)
        context = "\n\n".join(
            f"[{item.id}] {item.title}\n{item.content}\n知识点：{'、'.join(item.knowledge_points)}"
            for item in retrieved
        )
        system_prompt = self.common_system_prompt(
            "你负责相似题型训练。题目难度必须与用户目标院校的计算机专业课真题或常规模拟题对齐；"
            "未说明院校或科目时，默认按 408 难度，不能太偏、太难。",
            task="question_generation",
        )
        user_prompt = f"""
用户需求：
{request.message}

近期对话上下文：
{self.conversation_context(request)}

可参考题库：
{context or "本地题库暂无召回，请按用户指定科目命题；未指定时按 408 难度新编。"}

请输出：
0. 若用户要求“再出一道/同类型”，必须以上下文中的原题或知识点为锚点
1. 3 道相似训练题，标注科目、知识点、难度
2. 每题给出标准答案
3. 每题给出简明解析和踩分点
4. 说明它和原题/知识点的相似关系
"""
        answer = self.llm.generate(system_prompt, user_prompt, request.image_base64)
        return AgentResponse(
            intent=Intent.SIMILAR_TRAINING,
            answer=answer,
            citations=retrieved,
            next_actions=["提交作答", "查看逐题解析", "加入今日训练计划"],
        )
