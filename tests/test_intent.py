from kaoyan_ai.agents.intent import IntentAgent
from kaoyan_ai.schemas import AgentRequest, Intent


def test_image_routes_to_solution() -> None:
    request = AgentRequest(message="请看看这题", image_base64="abc")
    assert IntentAgent().classify(request) == Intent.SOLVE_QUESTION


def test_school_prediction_intent() -> None:
    request = AgentRequest(message="帮我预测一下某院校计算机专业分数线")
    assert IntentAgent().classify(request) == Intent.ADMISSION_PREDICTION
