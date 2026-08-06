from kaoyan_ai.agents.analysis import PersonalAnalysisAgent
from kaoyan_ai.agents.study_plan import StudyPlanAgent
from kaoyan_ai.agents.base import AgentBase
from kaoyan_ai.schemas import AgentRequest, AnswerRecord, UserProfile, WrongQuestion


def test_personal_analysis_outputs_charts() -> None:
    profile = UserProfile(
        user_id="u1",
        wrong_questions=[
            WrongQuestion(
                question_id="q1",
                subject="操作系统",
                knowledge_points=["页表"],
                error_reason="概念不清",
            )
        ],
        answer_records=[
            AnswerRecord(
                question_id="q1",
                subject="操作系统",
                knowledge_points=["页表"],
                is_correct=False,
            ),
            AnswerRecord(
                question_id="q2",
                subject="操作系统",
                knowledge_points=["快表"],
                is_correct=True,
            ),
        ],
    )
    response = PersonalAnalysisAgent().run(AgentRequest(message="分析我", profile=profile))
    # 图表数据仍然基于静态统计，一定会生成
    assert response.charts
    # 回答内容现在由 LLM 生成，只要有内容即可
    assert response.answer
    assert len(response.answer) > 50


def test_agents_inherit_from_agent_base() -> None:
    """确保 StudyPlanAgent 和 PersonalAnalysisAgent 都继承自 AgentBase。"""
    assert issubclass(StudyPlanAgent, AgentBase)
    assert issubclass(PersonalAnalysisAgent, AgentBase)
    # 确认拥有 LLM 和 SkillBook 实例
    agent = StudyPlanAgent()
    assert hasattr(agent, "llm")
    assert hasattr(agent, "skills")
    agent2 = PersonalAnalysisAgent()
    assert hasattr(agent2, "llm")
    assert hasattr(agent2, "skills")
