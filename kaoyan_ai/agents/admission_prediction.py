from __future__ import annotations

from statistics import mean
import re

from kaoyan_ai.agents.base import AgentBase
from kaoyan_ai.schemas import AgentRequest, AgentResponse, Intent, RetrievedItem
from kaoyan_ai.school_selection import SchoolSelectionRequest, analyze_school_selection


class AdmissionPredictionAgent(AgentBase):
    """预测院校专业分数趋势，并明确给出风险提示。"""

    def run(self, request: AgentRequest) -> AgentResponse:
        """根据用户提供的真实历史分数生成录取风险分析。"""

        school = (
            request.metadata.get("school")
            or self._extract_school(request.message)
            or self._extract_after(request.message, "院校")
        )
        major = request.metadata.get("major") or self._extract_after(request.message, "专业")
        historical_scores = request.metadata.get("historical_scores") or self._extract_scores(
            request.message
        )
        score_years = request.metadata.get("score_years") or self._extract_years(request.message)
        if school:
            research = analyze_school_selection(
                SchoolSelectionRequest(
                    school=school,
                    major=major or "计算机相关专业",
                    historical_scores=[float(score) for score in historical_scores],
                    score_years=score_years if len(score_years) == len(historical_scores) else [],
                    target_score=request.metadata.get("target_score"),
                ),
                llm=self.llm,
            )
            citations = [
                RetrievedItem(
                    id=f"school-source-{index}",
                    title=item["title"],
                    content=item.get("snippet") or item.get("source_label") or "",
                    subject="择校",
                    source=item["url"],
                )
                for index, item in enumerate(research.get("evidence", [])[:12], start=1)
            ]
            return AgentResponse(
                intent=Intent.ADMISSION_PREDICTION,
                answer=(
                    research["summary"]
                    + "\n\n> "
                    + research["methodology"]
                    + "\n\n"
                    + research["disclaimer"]
                ),
                citations=citations,
                next_actions=["查看独立智能择校页", "补充近三年拟录取名单", "生成目标分拆解"],
                metadata={
                    "school": school,
                    "major": major,
                    "trend": research["trend"],
                    "heat": research["heat"],
                    "risk": research["risk"],
                    "online_source_count": len(research.get("evidence", [])),
                },
            )
        predicted = (
            self._predict_score([float(score) for score in historical_scores])
            if historical_scores
            else None
        )

        system_prompt = self.common_system_prompt(
            "你负责院校专业分数预测。必须标注“仅供参考”，并提醒真实录取受招生名额、复试权重和生源变化影响。"
        )
        user_prompt = f"""
用户需求：{request.message}
院校：{school or "未指定"}
专业：{major or "未指定"}
近年分数线/拟录取最低分：{historical_scores or "未提供"}
趋势预测：{predicted or "数据不足，禁止给出伪精确预测"}

请输出：
1. 明确写“仅供参考”
2. 给出下一年分数区间预测
3. 分析复试对最终录取变化是否可能较大
4. 如果存在低分逆袭/高分被刷，列出可能原因
5. 给出择校风险等级和备考建议

注意：若没有可靠联网/榜单数据，必须说明当前基于用户提供或本地数据推断。
未提供真实历史数据时，只列出需要补充的数据，不得虚构预测分数。
"""
        answer = self.llm.generate(system_prompt, user_prompt)
        if "仅供参考" not in answer:
            prefix = "仅供参考：录取结果受招生名额、复试权重和生源变化影响。"
            if not historical_scores:
                prefix += " 当前缺少真实历史数据，不能给出可靠分数预测。"
            answer = f"{prefix}\n\n{answer}"
        return AgentResponse(
            intent=Intent.ADMISSION_PREDICTION,
            answer=answer,
            next_actions=["补充近三年拟录取名单", "生成择校对比表", "生成目标分拆解"],
            metadata={
                "predicted_score": predicted,
                "data_sufficient": len(historical_scores) >= 3,
                "sample_size": len(historical_scores),
            },
        )

    def _predict_score(self, scores: list[float]) -> dict[str, float]:
        """用“趋势 + 波动”基线估算下一年的分数区间。"""

        if not scores:
            return {"low": 0.0, "mid": 0.0, "high": 0.0}
        trend = scores[-1] - scores[0] if len(scores) >= 2 else 0
        annual_trend = trend / max(len(scores) - 1, 1)
        mid = scores[-1] + annual_trend * 0.6
        volatility = max(6.0, mean(abs(score - mean(scores)) for score in scores))
        return {"low": round(mid - volatility), "mid": round(mid), "high": round(mid + volatility)}

    def _extract_after(self, message: str, keyword: str) -> str | None:
        """从简单中文提示中尽量提取关键词后面的内容。"""

        if keyword not in message:
            return None
        tail = message.split(keyword, 1)[-1].strip("：: ，,。")
        return tail[:20] or None

    def _extract_school(self, message: str) -> str | None:
        match = re.search(r"([\u4e00-\u9fff]{2,16}(?:大学|学院))", message)
        return match.group(1) if match else None

    def _extract_scores(self, message: str) -> list[float]:
        values: list[float] = []
        for raw in re.findall(r"(?<!\d)([234]\d{2})(?!\d)", message):
            value = int(raw)
            if 200 <= value <= 450 and not 2010 <= value <= 2029:
                values.append(float(value))
        return values[:10]

    def _extract_years(self, message: str) -> list[int]:
        return [int(value) for value in re.findall(r"20[12]\d", message)][:10]
