from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量和 .env 文件读取项目配置。

    把配置集中在这里，可以让 API、智能体、RAG 和 MCP 使用同一套运行参数。
    本地开发时，即使机器环境里已有 API Key，也可以用 DISABLE_LLM 强制返回离线结果。
    """

    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4.1-mini"
    llm_provider: str = "dashscope"
    dashscope_api_key: str | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen3.8-max"
    dashscope_enable_thinking: bool = True
    dashscope_include_reasoning: bool = False
    glm_api_key: str | None = None
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    glm_model: str = "qwen3.8-max"
    glm_enable_thinking: bool = True
    glm_include_reasoning: bool = False
    llm_timeout_seconds: int = 15
    embedding_model: str = "text-embedding-3-small"
    rag_enable_embeddings: bool = False
    rag_embedding_index_dir: Path = Path("data/embeddings")
    disable_llm: bool = False
    app_env: str = "dev"
    rag_top_k: int = 5
    chat_strict_scope: bool = True
    chat_rag_question_k: int = 3
    chat_rag_knowledge_k: int = 4
    agent_max_iterations: int = 12
    agent_trace_enabled: bool = True
    agent_llm_planner_enabled: bool = True
    data_dir: Path = Path("data")
    skill_dir: Path = Path("skills")

    # JWT 鉴权
    jwt_secret: str = "kaoyan-ai-dev-secret-please-change-in-production"
    jwt_expires_hours: int = 24 * 7  # 7 天

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """返回缓存后的配置对象，保证各模块读取的是同一份配置快照。"""

    return Settings()
