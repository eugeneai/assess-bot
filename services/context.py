import logging
import re
from typing import Any

from services.llm import call_deepseek
from services.parser import extract_title_info

logger = logging.getLogger(__name__)


class ContextDetector:
    async def analyze(
        self,
        forward_chat_name: str | None = None,
        message_text: str = "",
        extracted_text: str = "",
        files_meta: list | None = None,
    ) -> dict[str, Any]:
        ctx: dict[str, Any] = {
            "student_name": None,
            "course": None,
            "lab": None,
            "confidence": 0.0,
            "needs_clarification": True,
            "practice": None,
            "group": None,
            "layers": {},
        }

        self._apply_layer1_rules(ctx, forward_chat_name, message_text, extracted_text, files_meta or [])

        self._apply_layer2_history(ctx)

        if ctx.get("confidence", 0) < 0.9:
            await self._apply_layer3_llm(ctx, forward_chat_name, message_text, extracted_text)

        if ctx.get("confidence", 0) >= 0.7 and ctx.get("student_name") and ctx.get("course") and ctx.get("lab"):
            ctx["needs_clarification"] = False

        return ctx

    def _apply_layer1_rules(
        self,
        ctx: dict,
        forward_chat_name: str | None,
        message_text: str,
        extracted_text: str,
        files_meta: list,
    ):
        hits = 0
        total = 5

        if forward_chat_name:
            match = re.search(r'[«"](.+?)[»"]', forward_chat_name)
            if match:
                ctx["course"] = match.group(1).strip()
                hits += 1

        combined = f"{message_text}\n{extracted_text}"

        title_info = extract_title_info(extracted_text)
        if title_info.get("practice"):
            ctx["practice"] = title_info["practice"]
            hits += 1
        if title_info.get("course"):
            ctx["course"] = ctx.get("course") or title_info["course"]
            hits += 1
        if title_info.get("group"):
            ctx["group"] = title_info["group"]

        lab_patterns = [
            r'Л[Рр]\s*(\d+)',
            r'[Ll][Aa][Bb]\s*(\d+)',
            r'лабораторн[аяойю]+?\s+работ[а-я]*\s*(\d+)',
            r'лаба\s*(\d+)',
        ]
        for pat in lab_patterns:
            match = re.search(pat, combined)
            if match:
                ctx["lab"] = f"ЛР{match.group(1)}"
                hits += 1
                break

        if not ctx.get("lab") and title_info.get("lab_numbers"):
            ctx["lab"] = f"ЛР{title_info['lab_numbers'][0]}"
            hits += 1

        course_patterns = [
            r'(?:по\s+)?курс[уеа]?\s*[«"](.+?)[»"]',
            r'(?:дисциплина|предмет)\s*[:\s]\s*(.+?)[\n,]',
        ]
        if not ctx.get("course"):
            for pat in course_patterns:
                match = re.search(pat, combined, re.IGNORECASE)
                if match:
                    ctx["course"] = match.group(1).strip()
                    hits += 1
                    break

        confidence = hits / total
        ctx["confidence"] = max(ctx.get("confidence", 0), confidence)
        ctx["layers"]["rules"] = {"hits": hits, "total": total, "confidence": confidence}

    def _apply_layer2_history(self, ctx: dict):
        pass

    async def _apply_layer3_llm(
        self,
        ctx: dict,
        forward_chat_name: str | None,
        message_text: str,
        extracted_text: str,
    ):
        try:
            prompt = (
                "Ты — ассистент, который определяет контекст лабораторной работы по данным из Telegram.\n\n"
                f"Название чата-источника: {forward_chat_name or 'неизвестно'}\n"
                f"Текст сообщения: {message_text[:500] or 'нет'}\n"
                f"Текст документа: {extracted_text[:1000] or 'нет'}\n\n"
                "Ответь строго в формате JSON:\n"
                '{"student_name": "ФИО студента или null", "course": "название курса или null", "lab": "название лабораторной или null", "practice": "название практики или null", "group": "группа или null", "confidence": 0.0-1.0}\n\n'
                "Если данных недостаточно — укажи null."
            )

            result = await call_deepseek(prompt, expect_json=True)

            if result:
                for key in ("student_name", "course", "lab", "practice", "group"):
                    if result.get(key):
                        ctx[key] = result[key]
                if "confidence" in result:
                    ctx["confidence"] = max(ctx.get("confidence", 0), result["confidence"])
                ctx["layers"]["llm"] = result
        except Exception as e:
            logger.warning("LLM context analysis failed: %s", e)
            ctx["layers"]["llm"] = {"error": str(e)}
