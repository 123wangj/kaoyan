from __future__ import annotations

from collections import Counter, defaultdict

from kaoyan_ai.agents.base import AgentBase
from kaoyan_ai.schemas import AgentRequest, AgentResponse, ChartSpec, Intent, UserProfile


class PersonalAnalysisAgent(AgentBase):
    """根据用户记录生成学习诊断，结合 LLM 输出个性化分析建议。"""

    def run(self, request: AgentRequest) -> AgentResponse:
        """返回掌握度、错误原因分类和可直接绘图的数据。"""

        profile = request.profile or UserProfile(user_id=request.user_id)
        mastery = self._mastery(profile)
        error_reasons = Counter(question.error_reason for question in profile.wrong_questions)

        mastery_lines = "\n".join(
            f"- {point}: {score:.0f}%" for point, score in sorted(mastery.items())
        )
        reason_lines = "\n".join(
            f"- {reason}: {count} 次" for reason, count in error_reasons.items()
        ) or "- 暂无错题原因记录"
        weak_points = [point for point, score in mastery.items() if score < 70]
        weak_text = "、".join(weak_points) if weak_points else "暂未发现明显薄弱点"

        # 构建统计摘要供 LLM 分析
        stats_summary = (
            f"知识点掌握度：\n{mastery_lines or '暂无数据'}\n\n"
            f"错误原因分类：\n{reason_lines}\n\n"
            f"薄弱知识点（<70%）：{weak_text}\n\n"
            f"总作答记录：{len(profile.answer_records)} 条\n"
            f"总错题数：{len(profile.wrong_questions)} 道\n"
            f"正确作答数：{sum(1 for r in profile.answer_records if r.is_correct)} 条"
        )

        # 如果有对话历史，附带
        history_text = request.metadata.get("conversation_history", "")
        if history_text:
            stats_summary += f"\n\n近期对话：\n{history_text}"
        semantic_memory = request.metadata.get("semantic_memory", "")
        if semantic_memory:
            stats_summary += f"\n\n长期学习记忆：\n{semantic_memory}"

        system_prompt = self.common_system_prompt(
            "你正在为学生提供个性化的学习分析报告。\n"
            "要求：\n"
            "1. 基于学生的作答数据和掌握度，给出深入的学习诊断。\n"
            "2. 分析错误原因的分布规律，指出最需要改进的方向。\n"
            "3. 针对薄弱知识点，给出具体的复习建议和优先级排序。\n"
            "4. 结合对话历史（如果有），分析学生近期的学习趋势。\n"
            "5. 使用 Markdown 格式输出，包含'学习诊断''改进建议''优先攻克'三个板块。"
        )

        user_prompt = f"请基于以下学习数据，为学生提供深入的分析报告：\n\n{stats_summary}"

        answer = self.llm.generate(system_prompt, user_prompt)

        charts = [
            ChartSpec(
                type="bar",
                title="知识点掌握度",
                labels=list(mastery.keys()),
                values=[round(value, 2) for value in mastery.values()],
            ),
            ChartSpec(
                type="pie",
                title="错误原因分类",
                labels=list(error_reasons.keys()) or ["暂无"],
                values=[float(value) for value in error_reasons.values()] or [1.0],
                unit="次",
            ),
        ]
        return AgentResponse(
            intent=Intent.PERSONAL_ANALYSIS,
            answer=answer,
            charts=charts,
            next_actions=["生成薄弱点训练", "生成 7 天补弱计划", "复盘错题本"],
        )

    def _mastery(self, profile: UserProfile) -> dict[str, float]:
        """根据正确作答和错题记录计算每个知识点的掌握度。"""

        stats: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for record in profile.answer_records:
            for point in record.knowledge_points:
                stats[point][1] += 1
                stats[point][0] += int(record.is_correct)
        for wrong in profile.wrong_questions:
            for point in wrong.knowledge_points:
                stats[point][1] += 1

        return {
            point: (correct / total) * 100 if total else 0.0
            for point, (correct, total) in stats.items()
        }
