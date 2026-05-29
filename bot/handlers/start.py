from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message

from core.config import settings
from core.database import get_session
from core.models import Course, Lab, Student, Submission

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    if message.chat.id != settings.group_id:
        return

    await message.answer(
        "👋 <b>Assess Bot</b>\n\n"
        "Я принимаю лабораторные работы студентов.\n\n"
        "📤 <b>Как использовать:</b>\n"
        "1. Перешлите (forward) сообщение от студента с файлами в эту группу\n"
        "2. Я проанализирую документы, определю студента, курс и лабу\n"
        "3. Если нужны уточнения — я задам вопрос, ответьте quote на моё сообщение\n\n"
        "📋 <b>Команды:</b>\n"
        "/review — список непроверенных работ\n"
        "/stats — статистика"
    )
