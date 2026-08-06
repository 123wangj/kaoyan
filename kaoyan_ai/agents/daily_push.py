from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from kaoyan_ai.agents.base import AgentBase, LLMClient
from kaoyan_ai.config import get_settings
from kaoyan_ai.question_enrichment import is_unlabeled_kp
from kaoyan_ai.question_quality import question_is_well_formed
from kaoyan_ai.rag import LocalRetriever
from kaoyan_ai.schemas import (
    AgentRequest,
    AgentResponse,
    DailyPushQuestion,
    DailyPushResult,
    Intent,
    UserProfile,
)


class DailyPushAgent(AgentBase):
    """根据用户近期薄弱知识点，用LLM生成不重复的每日推送和2道新选择题。"""

    def __init__(
        self,
        retriever: LocalRetriever | None = None,
        exam_insights: dict | None = None,
    ) -> None:
        super().__init__()
        self.retriever = retriever or LocalRetriever()
        self.exam_insights = exam_insights or {}

    def run(self, request: AgentRequest) -> AgentResponse:
        profile = request.profile or UserProfile(user_id=request.user_id)
        push_result = self._generate_daily_push(profile)

        answer = self._format_push_result(push_result)

        citations = []
        for q in push_result.questions:
            citations.append(
                self._to_retrieved_item(q)
            )

        return AgentResponse(
            intent=Intent.DAILY_PUSH,
            answer=answer,
            citations=citations,
            next_actions=["完成今日练习", "标记已掌握", "查看详细解析"],
            metadata={
                "push_result": push_result.model_dump(),
                "pushed_ids": [push_result.knowledge_point_id]
                           + [q.id for q in push_result.questions],
            },
        )

    def _generate_daily_push(self, profile: UserProfile) -> DailyPushResult:
        """主流程：识别薄弱知识点 → 选一个未推送过的 → 用LLM生成2道新题。"""

        weak_points = self._analyze_weak_points(profile)
        exam_points = []
        for item in self.exam_insights.get("weak_points") or []:
            title = str(item.get("name") or "").strip()
            subject = str(item.get("subject") or "").strip()
            if not title:
                continue
            evidence = str(item.get("evidence") or "").strip()
            action = str((item.get("action_plan") or [""])[0]).strip()
            content = self._lookup_knowledge_content(title, subject)
            if evidence or action:
                content = f"{content}\n\n最近试卷诊断：{evidence}\n今日补强建议：{action}".strip()
            exam_points.append((subject, title, content))
        if exam_points:
            exam_names = {title for _, title, _ in exam_points}
            weak_points = exam_points + [item for item in weak_points if item[1] not in exam_names]
        if not weak_points:
            weak_points = self._fallback_knowledge_points(profile)

        selected_kp = self._select_unpushed(weak_points, profile.pushed_knowledge_ids)
        if not selected_kp:
            selected_kp = weak_points[0]

        subject, kp_title, kp_content = selected_kp
        kp_content = self._expand_knowledge_content(subject, kp_title, kp_content)

        existing_question_ids = set(profile.pushed_question_ids)
        existing_questions_text = self._get_existing_questions_context(profile)

        questions = self._generate_questions_with_llm(
            subject=subject,
            kp_title=kp_title,
            kp_content=kp_content,
            existing_ids=existing_question_ids,
            existing_questions_text=existing_questions_text,
        )

        kp_id = self._make_kp_id(subject, kp_title)

        return DailyPushResult(
            knowledge_point_title=kp_title,
            knowledge_point_content=kp_content,
            subject=subject,
            questions=questions,
            knowledge_point_id=kp_id,
        )

    def _analyze_weak_points(
        self, profile: UserProfile
    ) -> list[tuple[str, str, str]]:
        """从作答记录和错题中提取薄弱知识点，按错误率排序。"""

        stats: dict[str, dict] = defaultdict(lambda: {"correct": 0, "total": 0, "subject": ""})
        for record in profile.answer_records:
            for kp in record.knowledge_points:
                if is_unlabeled_kp(kp):
                    continue
                key = kp
                stats[key]["total"] += 1
                stats[key]["subject"] = record.subject
                if record.is_correct:
                    stats[key]["correct"] += 1

        for wrong in profile.wrong_questions:
            for kp in wrong.knowledge_points:
                if is_unlabeled_kp(kp):
                    continue
                key = kp
                stats[key]["total"] += 1
                stats[key]["subject"] = wrong.subject

        scored = []
        for kp, s in stats.items():
            accuracy = s["correct"] / s["total"] if s["total"] > 0 else 0.0
            weakness = 1.0 - accuracy
            scored.append((weakness, s["subject"], kp, s["total"]))

        scored.sort(key=lambda x: (-x[0], -x[3]))

        # 从知识库中查找知识点的详细内容
        results = []
        seen = set()
        for _, subject, kp_title, _ in scored:
            if kp_title in seen:
                continue
            seen.add(kp_title)
            content = self._lookup_knowledge_content(kp_title, subject)
            results.append((subject, kp_title, content))

        return results

    def _lookup_knowledge_content(
        self, kp_title: str, subject: str
    ) -> str:
        """从知识库中查找知识点详情。"""
        try:
            hits = self.retriever.retrieve(
                kp_title, collection="knowledge_points", subject=subject, k=3
            )
            if hits:
                return hits[0].content[:900]
        except Exception:
            pass
        return kp_title

    def _expand_knowledge_content(self, subject: str, kp_title: str, content: str) -> str:
        """把粗略知识点补全为复习卡片，不额外占用一次远程模型调用。"""
        if content and len(content) >= 180 and content != kp_title:
            return content[:900]

        base = (content or "").strip()
        if not base or base == kp_title:
            base = f"{kp_title}是{subject}复习中的核心知识点。"
        return (
            f"{base}\n\n"
            f"今日复习建议：先准确说出“{kp_title}”的定义与适用条件，再梳理关键规律、"
            "典型解题步骤和常见边界情况。做题时重点检查概念是否混淆、条件是否遗漏，"
            "并在完成练习后用一句话总结本题对应的易错点。"
        )[:900]

    def _fallback_knowledge_points(
        self, profile: UserProfile
    ) -> list[tuple[str, str, str]]:
        """当没有答题记录时，从知识库和chat_summary中推测。"""
        fallback_subjects = ["数据结构", "计算机组成原理", "操作系统", "计算机网络"]
        summary = profile.chat_summary or "408 核心知识点"

        results = []
        seen = set()
        try:
            hits = self.retriever.retrieve(summary, collection="knowledge_points", k=8)
            for item in hits:
                if item.subject not in seen and item.title:
                    seen.add(item.subject)
                    results.append(
                        (item.subject, item.title, item.content[:300])
                    )
        except Exception:
            pass

        if not results:
            for subj in fallback_subjects:
                results.append((subj, f"{subj}核心概念", f"请回顾{subj}的基础知识。"))

        return results

    def _select_unpushed(
        self,
        weak_points: list[tuple[str, str, str]],
        pushed_ids: list[str],
    ) -> tuple[str, str, str] | None:
        """选出还未推送过的知识点。"""
        for subject, title, content in weak_points:
            kp_id = self._make_kp_id(subject, title)
            if kp_id not in pushed_ids:
                return (subject, title, content)

        for subject, title, content in weak_points:
            return (subject, title, content)
        return None

    def _make_kp_id(self, subject: str, title: str) -> str:
        raw = f"{subject}:{title}"
        return "kp-" + hashlib.md5(raw.encode()).hexdigest()[:12]

    def _get_existing_questions_context(self, profile: UserProfile) -> str:
        """收集用户已做过的题目信息，避免生成重复题目。"""
        parts = []
        for record in profile.answer_records:
            qid = record.question_id
            kps = "、".join(record.knowledge_points)
            status = "正确" if record.is_correct else "错误"
            parts.append(f"- 题目[{qid}]（{status}）：涉及知识点 {kps}")

        for wrong in profile.wrong_questions:
            kps = "、".join(wrong.knowledge_points)
            parts.append(
                f"- 错题[{wrong.question_id}]：涉及知识点 {kps}，原因：{wrong.error_reason}"
            )

        return "\n".join(parts) if parts else "暂无历史作答记录"

    def _generate_questions_with_llm(
        self,
        subject: str,
        kp_title: str,
        kp_content: str,
        existing_ids: set[str],
        existing_questions_text: str,
    ) -> list[DailyPushQuestion]:
        """调用LLM生成2道与知识点相关的、不重复的选择题。"""

        system_prompt = (
            "你是计算机考研408命题专家。你擅长根据给定的知识点，"
            "生成高质量、有区分度的选择题。\n"
            "要求：\n"
            "1. 只生成选择题（4个选项 A/B/C/D）\n"
            "2. 题目必须紧扣给定知识点\n"
            "3. 题目不能与用户已做过的题目重复（考察内容、题干场景不能相同）\n"
            "4. 选项设计要有干扰性，符合考研命题风格\n"
            "5. 需给出正确答案和详细解析\n"
            "6. 严格按照以下JSON数组格式输出，不要输出其他内容：\n"
            '[\n'
            '  {\n'
            '    "content": "题干",\n'
            '    "options": ["A. 选项A", "B. 选项B", "C. 选项C", "D. 选项D"],\n'
            '    "answer": "A",\n'
            '    "explanation": "解析内容"\n'
            '  }\n'
            ']\n'
            "7. 参考408统考真题和《王道考研》系列教材的命题风格"
        )

        user_prompt = f"""
请为以下知识点生成2道全新的选择题（不要和用户已做过的题目重复）：

【科目】：{subject}
【知识点】：{kp_title}
【知识点详情】：{kp_content}

用户已经做过的题目如下（请避免出相同或类似的题目）：
{existing_questions_text}

请严格按JSON数组格式输出2道选择题。
"""

        try:
            result_text = LLMClient().generate(system_prompt, user_prompt)
        except Exception:
            return self._fallback_questions(subject, kp_title)

        questions = self._parse_llm_questions(result_text, subject, kp_title, existing_ids)
        return questions

    def _parse_llm_questions(
        self,
        result_text: str,
        subject: str,
        kp_title: str,
        existing_ids: set[str],
    ) -> list[DailyPushQuestion]:
        """解析LLM返回的JSON，转为 DailyPushQuestion 列表。"""
        json_match = re.search(r'\[[\s\S]*\]', result_text)
        if not json_match:
            return self._fallback_questions(subject, kp_title)

        try:
            raw_questions = json.loads(json_match.group(0))
        except json.JSONDecodeError:
            return self._fallback_questions(subject, kp_title)

        questions = []
        for raw in raw_questions:
            content = raw.get("content", "").strip()
            options = raw.get("options", [])
            answer = raw.get("answer", "").strip().upper()
            explanation = raw.get("explanation", "").strip()

            if not content or len(options) != 4 or answer not in {"A", "B", "C", "D"}:
                continue

            qid = self._make_question_id(subject, content)
            if qid in existing_ids:
                continue

            questions.append(
                DailyPushQuestion(
                    id=qid,
                    subject=subject,
                    knowledge_point=kp_title,
                    content=content,
                    options=options,
                    answer=answer,
                    explanation=explanation,
                )
            )

        if not questions:
            return self._fallback_questions(subject, kp_title)

        return questions[:2]

    def _make_question_id(self, subject: str, content: str) -> str:
        raw = f"{subject}:{content[:50]}"
        return "push-q-" + hashlib.md5(raw.encode()).hexdigest()[:12]

    def _fallback_questions(
        self, subject: str, kp_title: str
    ) -> list[DailyPushQuestion]:
        """Use complete local question-bank rows when LLM generation fails."""
        try:
            path = Path(get_settings().data_dir) / "question_bank.jsonl"
            if not path.exists():
                return []
            rows = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            exact = [
                row
                for row in rows
                if row.get("subject") == subject
                and kp_title in (row.get("knowledge_points") or [])
                and question_is_well_formed(row)
                and len(row.get("options") or []) == 4
                and str(row.get("answer") or "").strip().upper()[:1] in {"A", "B", "C", "D"}
            ]
            # Do not relabel a merely same-subject question as the requested
            # knowledge point. If there is no verified exact mapping, abstain.
            candidates = exact
            candidates.sort(
                key=lambda row: hashlib.sha1(
                    f"{subject}|{kp_title}|{row.get('id')}".encode("utf-8")
                ).hexdigest()
            )
            return [
                DailyPushQuestion(
                    id="fallback-" + str(row.get("id")),
                    subject=subject,
                    knowledge_point=kp_title,
                    content=str(row.get("content") or row.get("title") or ""),
                    options=[str(option) for option in row.get("options") or []],
                    answer=str(row.get("answer") or "").strip().upper()[:1],
                    explanation=str(row.get("explanation") or row.get("analysis") or ""),
                )
                for row in candidates[:2]
            ]
        except Exception:
            return []

    def _format_push_result(self, result: DailyPushResult) -> str:
        lines = [
            f"## 📚 今日知识点",
            f"",
            f"**科目**：{result.subject}",
            f"",
            f"### {result.knowledge_point_title}",
            f"",
            f"{result.knowledge_point_content}",
        ]

        if result.questions:
            lines.extend([
                "",
                "---",
                "",
                "## 🎯 今日练习（选择题）",
                "",
            ])
            for i, q in enumerate(result.questions, 1):
                lines.extend([
                    f"### 第{i}题",
                    f"",
                    q.content,
                    "",
                ])
                for opt in q.options:
                    lines.append(opt)
                lines.append("")

            lines.extend([
                "---",
                "",
                "💡 点击上方「完成今日练习」按钮提交你的答案，系统会自动批改并给出解析。",
            ])

        return "\n".join(lines)

    def _to_retrieved_item(self, q: DailyPushQuestion):
        from kaoyan_ai.schemas import RetrievedItem

        return RetrievedItem(
            id=q.id,
            title=f"[每日一题] {q.subject} - {q.knowledge_point}",
            content=f"{q.content}\n" + "\n".join(q.options),
            subject=q.subject,
            knowledge_points=[q.knowledge_point],
            difficulty="中等",
            source="daily_push",
        )
