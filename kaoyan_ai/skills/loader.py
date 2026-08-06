from __future__ import annotations

from pathlib import Path

from kaoyan_ai.config import get_settings


class SkillBook:
    """Loads local markdown skills used as reusable prompt policies."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_settings().skill_dir

    def load(self, name: str) -> str:
        """按文件夹名称加载一个 Skill 提示词。"""

        path = self.root / name / "SKILL.md"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def compose(self, *names: str) -> str:
        """把多个 Skill 提示词拼接成一个系统策略块。"""

        return "\n\n".join(skill for name in names if (skill := self.load(name)))

    def select(
        self,
        *,
        task: str,
        mastery_score: float | None = None,
        preference: str = "",
    ) -> list[str]:
        """Select teaching strategies from task and learner evidence."""

        selected = ["408_exam_scope", "scoring_steps"]
        if task in {"recitation", "explanation"}:
            selected.append("vivid_explanation")
        if mastery_score is not None and mastery_score < 55:
            selected.append("guided_questioning")
        if "简洁" in preference:
            selected.append("concise_response")
        if task in {"solution", "question_generation"}:
            selected.append("answer_verification")
        return list(dict.fromkeys(selected))
