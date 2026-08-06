from __future__ import annotations

from kaoyan_ai.graph import KaoyanTutorGraph
from kaoyan_ai.rag import LocalRetriever
from kaoyan_ai.schemas import AgentRequest


def main() -> None:
    """启动 MCP 服务，对外暴露智能体问答和题库检索工具。"""

    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("kaoyan-cs-ai")
    graph = KaoyanTutorGraph()
    retriever = LocalRetriever()

    @mcp.tool()
    def search_408_question_bank(query: str, k: int = 5) -> list[dict]:
        """检索本地 408 题库和知识点片段。"""
        return [item.model_dump() for item in retriever.retrieve(query, k=k)]

    @mcp.tool()
    def ask_kaoyan_tutor(user_id: str, message: str) -> dict:
        """调用 LangGraph 辅导智能体并返回结构化结果。"""
        response = graph.run(AgentRequest(user_id=user_id, message=message))
        return response.model_dump()

    mcp.run()


if __name__ == "__main__":
    main()
