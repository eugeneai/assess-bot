import logging
from pathlib import Path
from typing import Any

from core.config import settings
from services.llm import call_deepseek
from services.review import load_prompt, global_prompt_path, course_prompt_path, save_prompt

logger = logging.getLogger(__name__)


class AssessmentAgent:
    def __init__(self):
        self.training_data: list[dict] = []

    def _ensure_prompt_files(self, course_slug: str | None = None):
        gp_path = global_prompt_path()
        if not Path(gp_path).exists():
            save_prompt(gp_path, "# Глобальные требования\n\nДополните общие критерии оценки.")
            logger.info("Created default global prompt at %s", gp_path)

        if course_slug:
            cp_path = course_prompt_path(course_slug)
            if not Path(cp_path).exists():
                save_prompt(cp_path, f"# Требования курса\n\nДополните критерии оценки для этого курса.")
                logger.info("Created default course prompt at %s", cp_path)

    async def suggest(
        self,
        extracted_text: str,
        course_slug: str | None = None,
    ) -> dict[str, Any] | None:
        if not extracted_text or len(extracted_text.strip()) < 50:
            return None

        self._ensure_prompt_files(course_slug)
        examples = self.training_data[-5:] if self.training_data else []

        global_prompt = load_prompt(global_prompt_path())
        course_prompt = load_prompt(course_prompt_path(course_slug)) if course_slug else None

        prompt_parts = []
        prompt_parts.append("Ты — ассистент преподавателя. Оцени лабораторную работу студента по 100-балльной шкале.\n")

        if global_prompt:
            prompt_parts.append(f"--- ОБЩИЕ ТРЕБОВАНИЯ ---\n{global_prompt}\n")

        if course_prompt:
            prompt_parts.append(f"--- ТРЕБОВАНИЯ К КУРСУ ---\n{course_prompt}\n")

        prompt_parts.append(
            "Базовые критерии оценки:\n"
            "1. Полнота выполнения задания (0-40)\n"
            "2. Качество оформления отчёта (0-20)\n"
            "3. Глубина анализа (0-20)\n"
            "4. Корректность выводов (0-20)\n"
        )

        if examples:
            prompt_parts.append("Примеры предыдущих оценок:\n")
            for ex in examples:
                prompt_parts.append(f"- Оценка: {ex['grade']}/100, Комментарий: {ex.get('feedback', '')}")
            prompt_parts.append("")

        prompt_parts.append(f"Текст работы:\n{extracted_text[:2000]}\n")
        prompt_parts.append(
            "Ответь строго в формате JSON:\n"
            '{"grade": <число 0-100>, "reasoning": "<краткое обоснование>"}'
        )

        prompt = "\n".join(prompt_parts)

        try:
            result = await call_deepseek(prompt, expect_json=True)
            if result and "grade" in result:
                grade = int(result["grade"])
                grade = max(0, min(100, grade))
                return {
                    "grade": grade,
                    "reasoning": result.get("reasoning", ""),
                }
            return None
        except Exception as e:
            logger.warning("Assessment agent failed: %s", e)
            return None

    async def train(self, submission_id: int, grade: int, feedback: str):
        from core.database import get_session
        from core.models import Submission

        async with await get_session() as session:
            sub = await session.get(Submission, submission_id)
            if sub and sub.extracted_text:
                self.training_data.append({
                    "text": sub.extracted_text[:2000],
                    "grade": grade,
                    "feedback": feedback,
                    "submission_id": submission_id,
                })
