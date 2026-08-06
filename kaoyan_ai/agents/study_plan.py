from __future__ import annotations

from datetime import date, datetime
import json

from kaoyan_ai.agents.base import AgentBase
from kaoyan_ai.schemas import AgentRequest, AgentResponse, Intent, UserProfile


class StudyPlanAgent(AgentBase):
    """根据薄弱点和剩余天数生成日、周、月复习计划。"""

    def run(self, request: AgentRequest) -> AgentResponse:
        """根据用户当前复习阶段生成结构化学习计划。"""

        profile = request.profile or UserProfile(user_id=request.user_id)
        days_left = self._days_left(profile.exam_date, request.metadata.get("days_left"))
        weak_points = self._weak_points(profile)
        phase = self._phase(days_left)
        weak_text = "、".join(weak_points) if weak_points else "目标院校计算机专业课基础体系"

        # 构建基础上下文
        context = (
            f"剩余时间：约 {days_left} 天\n"
            f"当前阶段：{phase}\n"
            f"重点薄弱点：{weak_text}\n"
            f"错题数量：{len(profile.wrong_questions)} 道\n"
            f"作答记录：{len(profile.answer_records)} 条"
        )

        # 如果有对话历史，附带
        history_text = request.metadata.get("conversation_history", "")
        if history_text:
            context += f"\n\n近期对话：\n{history_text}"
        semantic_memory = request.metadata.get("semantic_memory", "")
        if semantic_memory:
            context += f"\n\n长期学习记忆：\n{semantic_memory}"
        executable_plan = request.metadata.get("executable_study_plan")
        if executable_plan:
            compact_plan = {
                "week_count": executable_plan.get("week_count"),
                "total_tasks": executable_plan.get("total_tasks"),
                "weak_subjects": executable_plan.get("weak_subjects"),
                "first_week": (executable_plan.get("weekly") or [{}])[0],
            }
            context += (
                "\n\n系统已生成并保存以下可执行计划。请解释安排依据和第一周执行方式，"
                "不要重新编造另一份计划：\n"
                + json.dumps(compact_plan, ensure_ascii=False)
            )

        system_prompt = self.common_system_prompt(
            "你正在为学生制定个性化的计算机专业考研复习计划。优先服从用户明确给出的院校与考试科目；"
            "用户未说明专业课科目时再按 408 规划。\n"
            "要求：\n"
            "1. 根据学生的薄弱知识点和剩余天数，给出具体可执行的日/周/月计划。\n"
            "2. 计划要具体到每天的学习任务量（如多少道题、复习哪些章节）。\n"
            "3. 优先攻克薄弱点，同时保持强项的熟练度。\n"
            "4. 使用 Markdown 格式输出，结构清晰。\n"
            "5. 如果有对话历史，结合学生之前的问题来调整计划重点。"
        )

        user_prompt = f"请根据以下学生信息制定详细的计算机专业考研复习计划：\n\n{context}"

        answer = self.llm.generate(system_prompt, user_prompt)

        return AgentResponse(
            intent=Intent.STUDY_PLAN,
            answer=answer,
            next_actions=["导出日历", "生成今日任务清单", "按薄弱点生成训练题"],
            metadata={
                "days_left": days_left,
                "phase": phase,
                "weak_points": weak_points,
                "plan_saved": bool(executable_plan),
                "plan_schema_version": (
                    executable_plan.get("schema_version") if executable_plan else None
                ),
            },
        )

    def _days_left(self, exam_date: str | None, fallback: int | None) -> int:
        """优先使用显式传入天数，其次使用画像考试日期，最后使用默认值。"""

        if fallback:
            return int(fallback)
        if exam_date:
            target = datetime.strptime(exam_date, "%Y-%m-%d").date()
            return max((target - date.today()).days, 1)
        return 180

    def _weak_points(self, profile: UserProfile) -> list[str]:
        """按错题中出现频次对薄弱知识点排序。"""

        counts: dict[str, int] = {}
        for wrong in profile.wrong_questions:
            for point in wrong.knowledge_points:
                counts[point] = counts.get(point, 0) + 1
        return [point for point, _ in sorted(counts.items(), key=lambda pair: pair[1], reverse=True)[:5]]

    def _phase(self, days_left: int) -> str:
        """把剩余天数映射到常见的考研复习阶段。"""

        if days_left > 180:
            return "基础搭建期"
        if days_left > 90:
            return "强化训练期"
        if days_left > 30:
            return "真题与套卷期"
        return "冲刺查漏期"
