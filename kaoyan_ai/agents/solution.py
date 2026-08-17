from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from kaoyan_ai.agents.base import AgentBase
from kaoyan_ai.rag import LocalRetriever
from kaoyan_ai.schemas import AgentRequest, AgentResponse, Intent, RetrievedItem


class SolutionAgent(AgentBase):
    """结合 RAG 参考资料解答用户上传或粘贴的 408 题目。"""

    def __init__(self, retriever: LocalRetriever | None = None) -> None:
        super().__init__()
        self.retriever = retriever or LocalRetriever()

    def run(self, request: AgentRequest) -> AgentResponse:
        """召回相关例题，并要求模型给出带踩分点的讲解。"""

        retrieval_query = self.contextual_retrieval_query(request)
        # The two collections are independent. Retrieve them concurrently while
        # preserving the same evidence set and final ordering used before.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="chat-rag") as pool:
            question_future = pool.submit(
                self.retriever.retrieve,
                retrieval_query,
                collection="question_bank",
                k=3,
            )
            knowledge_future = pool.submit(
                self.retriever.retrieve,
                retrieval_query,
                collection="knowledge_points",
                k=4,
            )
            question_hits = question_future.result()
            knowledge_hits = knowledge_future.result()
        retrieved = []
        seen: set[tuple[str, str]] = set()
        for item in question_hits + knowledge_hits:
            key = (item.id, item.content[:120])
            if key not in seen:
                seen.add(key)
                retrieved.append(item)
        context = self._format_context(retrieved)
        system_prompt = self.common_system_prompt(
            "你负责计算机专业考研题目解答。先判断所属考试科目；可以处理 408 和院校自命题专业课。",
            task="solution",
        )
        user_prompt = f"""
用户题目：
{request.message}

近期对话上下文：
{self.conversation_context(request)}

长期学习偏好：
{request.metadata.get("semantic_memory") or "暂无稳定偏好记录"}

RAG 参考资料：
{context}

请按以下结构回答：
0. 如果当前问题是追问，先结合近期对话明确它所指的概念或步骤，不要把它当成孤立问题
1. 科目、章节、核心考点与题型判断
2. 最终答案
3. 解题思路，按考研阅卷踩分点写清楚每一步
4. 生动解释，用类比或小例子帮助理解
5. 易错点提醒
6. 可继续训练的 2 个知识点
"""
        answer = self.llm.generate(system_prompt, user_prompt, request.image_base64)
        return AgentResponse(
            intent=Intent.SOLVE_QUESTION,
            answer=answer,
            citations=retrieved,
            next_actions=["生成相似题训练", "加入错题本", "生成该知识点带背卡片"],
        )

    def _format_context(self, items: list[RetrievedItem]) -> str:
        """把召回结果整理成紧凑的提示词上下文。"""

        if not items:
            return "暂无本地召回资料，请基于 408 考纲谨慎作答。"
        return "\n\n".join(
            f"[{item.id}] {item.title}\n科目：{item.subject}\n内容：{item.content}\n踩分点："
            f"{'；'.join(item.score_points) or '暂无'}"
            for item in items
        )
