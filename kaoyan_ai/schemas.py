from __future__ import annotations

from enum import Enum
from datetime import datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


CS408_SUBJECTS = ("数据结构", "计算机组成原理", "操作系统", "计算机网络")


class Intent(str, Enum):
    """主路由智能体支持的全部用户意图。"""

    SOLVE_QUESTION = "solve_question"
    SIMILAR_TRAINING = "similar_training"
    PERSONAL_ANALYSIS = "personal_analysis"
    RECITATION = "recitation"
    DAILY_PUSH = "daily_push"
    ADMISSION_PREDICTION = "admission_prediction"
    STUDY_PLAN = "study_plan"
    FALLBACK = "fallback"


class RetrievedItem(BaseModel):
    """从本地题库或知识库召回的一条 RAG 结果。"""

    id: str
    title: str = ""
    content: str
    subject: str = ""
    knowledge_points: list[str] = Field(default_factory=list)
    difficulty: Literal["基础", "中等", "较难"] = "中等"
    source: str = "local"
    score_points: list[str] = Field(default_factory=list)


class WrongQuestion(BaseModel):
    """一条错题记录，用于推断用户薄弱知识点。"""

    question_id: str
    subject: str
    knowledge_points: list[str] = Field(default_factory=list)
    error_reason: Literal["概念不清", "计算错误", "不会应用"] = "概念不清"
    created_at: str | None = None


class AnswerRecord(BaseModel):
    """一条平台作答记录，用于计算知识点掌握度。"""

    question_id: str
    subject: str
    knowledge_points: list[str] = Field(default_factory=list)
    is_correct: bool
    spent_seconds: int | None = None
    created_at: str | None = None


class DailyPushQuestion(BaseModel):
    """每日推送中生成的新题目。"""

    id: str
    subject: str
    knowledge_point: str
    content: str
    options: list[str]
    answer: str
    explanation: str
    image_url: str | None = None
    images: list[str] = Field(default_factory=list)


class UserProfile(BaseModel):
    """由聊天摘要、错题和作答记录组成的用户学习画像。"""

    user_id: str
    target_school: str | None = None
    target_major: str | None = None
    exam_date: str | None = None
    chat_summary: str = ""
    wrong_questions: list[WrongQuestion] = Field(default_factory=list)
    answer_records: list[AnswerRecord] = Field(default_factory=list)
    pushed_knowledge_ids: list[str] = Field(default_factory=list)
    pushed_question_ids: list[str] = Field(default_factory=list)


class DailyPushResult(BaseModel):
    """每日推送的返回结果。"""

    knowledge_point_title: str
    knowledge_point_content: str
    subject: str
    questions: list[DailyPushQuestion] = Field(default_factory=list)
    knowledge_point_id: str = ""


class AgentRequest(BaseModel):
    """所有智能体和 API 入口共用的统一请求对象。"""

    user_id: str = "anonymous"
    message: str
    image_base64: str | None = None
    intent_hint: Intent | None = None
    profile: UserProfile | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChartSpec(BaseModel):
    """面向前端展示的图表数据结构。"""

    type: Literal["bar", "radar", "pie", "line"]
    title: str
    labels: list[str]
    values: list[float]
    unit: str = "%"


class AgentResponse(BaseModel):
    """所有子智能体返回的统一响应对象。"""

    intent: Intent
    answer: str
    citations: list[RetrievedItem] = Field(default_factory=list)
    charts: list[ChartSpec] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanStep(BaseModel):
    """Agent 为完成一个用户目标生成的可执行步骤。"""

    id: str
    title: str
    intent: Intent
    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    requires_approval: bool = False
    success_criteria: str = ""
    error: str | None = None


class ToolCall(BaseModel):
    """一次可审计的内部工具调用。"""

    id: str
    run_id: str
    step_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class ToolResult(BaseModel):
    """内部工具的统一返回结构。"""

    call_id: str
    tool_name: str
    success: bool
    output: Any = None
    error: str | None = None
    evidence: list[RetrievedItem] = Field(default_factory=list)
    duration_ms: int = 0


class AgentRunTrace(BaseModel):
    """面向调试和评测的 Agent 运行轨迹。"""

    run_id: str
    user_id: str
    goal: str
    plan: list[PlanStep] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    iteration_count: int = 0
    confidence: float = 0.0
    status: Literal["running", "completed", "failed", "needs_approval"] = "running"
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    finished_at: str | None = None
    validation: dict[str, Any] = Field(default_factory=dict)


class AgentState(TypedDict, total=False):
    """LangGraph 节点之间传递的状态对象。"""

    request: AgentRequest
    intent: Intent
    goal: str
    plan: list[PlanStep]
    current_step: int
    tool_calls: list[ToolCall]
    observations: list[ToolResult]
    confidence: float
    iteration_count: int
    pending_approval: bool
    retrieved: list[RetrievedItem]
    response: AgentResponse
