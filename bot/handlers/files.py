import logging

from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select

from core.config import settings
from core.database import get_session
from core.models import Course, Lab, Student, Submission
from services.parser import extract_text_from_file
from services.storage import save_uploaded_file
from services.context import ContextDetector
from services.student_id import extract_student_name

logger = logging.getLogger(__name__)

router = Router()
context_detector = ContextDetector()


async def create_or_get_course(session, title):
    result = await session.execute(select(Course).where(Course.title.ilike(title)))
    course = result.scalar_one_or_none()
    if not course:
        course = Course(title=title)
        session.add(course)
        await session.commit()
        await session.refresh(course)
    return course


async def create_or_get_lab(session, course_id, title):
    result = await session.execute(
        select(Lab).where(Lab.course_id == course_id, Lab.title.ilike(title))
    )
    lab = result.scalar_one_or_none()
    if not lab:
        lab = Lab(course_id=course_id, title=title)
        session.add(lab)
        await session.commit()
        await session.refresh(lab)
    return lab


async def create_or_get_student(session, full_name):
    result = await session.execute(
        select(Student).where(Student.full_name.ilike(full_name))
    )
    student = result.scalar_one_or_none()
    if not student:
        student = Student(full_name=full_name)
        session.add(student)
        await session.commit()
        await session.refresh(student)
    return student


@router.message(F.chat.id == settings.group_id, F.forward_origin)
async def handle_forwarded(message: Message):
    if not message.forward_origin:
        return

    await message.answer("⏳ Анализирую полученную работу...")

    forward_chat_name = None
    if message.forward_origin.chat:
        forward_chat_name = message.forward_origin.chat.title

    raw_text = message.text or message.caption or ""
    files_meta = []
    extracted_text = ""

    if message.document:
        file_path = await save_uploaded_file(message.bot, message.document)
        files_meta.append({
            "file_id": message.document.file_id,
            "file_name": message.document.file_name,
            "file_path": file_path,
            "file_size": message.document.file_size,
            "mime_type": message.document.mime_type,
        })
        text = await extract_text_from_file(file_path, message.document.file_name or "")
        if text:
            extracted_text += text + "\n"

    if not files_meta and not raw_text.strip():
        await message.answer("⚠️ Не вижу файлов или текста в сообщении.")
        return

    ctx = await context_detector.analyze(
        forward_chat_name=forward_chat_name,
        message_text=raw_text,
        extracted_text=extracted_text,
        files_meta=files_meta,
    )

    student_name = extract_student_name(extracted_text) or ctx.get("student_name")
    course_guess = ctx.get("course")
    lab_guess = ctx.get("lab")
    confidence = ctx.get("confidence", 0)
    needs_clarification = ctx.get("needs_clarification", False)

    summary = (
        f"📥 <b>Получена работа</b>\n\n"
        f"👤 <b>Студент:</b> {student_name or '❓ Не определён'}\n"
        f"📚 <b>Курс:</b> {course_guess or '❓ Не определён'}\n"
        f"🔬 <b>Лаба:</b> {lab_guess or '❓ Не определён'}\n\n"
        f"📊 Уверенность: {int(confidence * 100)}%"
    )

    if not needs_clarification and student_name and course_guess and lab_guess:
        bot_msg = await message.answer(
            f"{summary}\n\n✅ <b>Работа сохранена:</b>"
        )

        async with await get_session() as session:
            course = await create_or_get_course(session, course_guess)
            lab = await create_or_get_lab(session, course.id, lab_guess)
            student = await create_or_get_student(session, student_name)

            submission = Submission(
                lab_id=lab.id,
                student_id=student.id,
                pending=False,
                forwarded_message_id=message.message_id,
                forwarded_chat_id=message.chat.id,
                bot_message_id=bot_msg.message_id,
                raw_text=raw_text,
                files_meta=files_meta,
                extracted_text=extracted_text,
                context=ctx,
            )
            session.add(submission)
            await session.commit()
    else:
        bot_msg = await message.answer(
            f"{summary}\n\n"
            f"⚠️ <b>Нужно уточнение.</b>\n"
            f"Ответьте на это сообщение, указав недостающие данные.\n"
            f"Например: <i>Студент: Петров, Курс: Python, Лаба: ЛР2</i>"
        )

        async with await get_session() as session:
            submission = Submission(
                pending=True,
                forwarded_message_id=message.message_id,
                forwarded_chat_id=message.chat.id,
                bot_message_id=bot_msg.message_id,
                raw_text=raw_text,
                files_meta=files_meta,
                extracted_text=extracted_text,
                context=ctx,
            )
            session.add(submission)
            await session.commit()
