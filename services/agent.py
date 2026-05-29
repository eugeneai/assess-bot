import logging
from typing import Any

from services.llm import call_deepseek

logger = logging.getLogger(__name__)


class AssessmentAgent:
    def __init__(self):
        self.training_data: list[dict] = []

    async def suggest(self, extracted_text: str) -> dict[str, Any] | None:
        if not extracted_text or len(extracted_text.strip()) < 50:
            return None

        examples = self.training_data[-5:] if self.training_data else []

        prompt = (
            "Ты — ассистент преподавателя. Оцени лабораторную работу студента по 100-балльной шкале.\n\n"
            "Критерии оценки:\n"
            "1. Полнота выполнения задания (0-40)\n"
            "2. Качество оформления отчёта (0-20)\n"
            "3. Глубина анализа (0-20)\n"
            "4. Корректность выводов (0-20)\n\n"
        )

        if examples:
            prompt += "Примеры предыдущих оценок:\n"
            for ex in examples:
                prompt += f"- Оценка: {ex['grade']}/100, Комментарий: {ex.get('feedback', '')}\n"
            prompt += "\n"

        prompt += (
            f"Текст работы:\n{extracted_text[:2000]}\n\n"
            "Ответь строго в формате JSON:\n"
            '{"grade": <число 0-100>, "reasoning": "<краткое обоснование>"}'
        )

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
