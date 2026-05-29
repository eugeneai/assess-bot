import logging

from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select

from core.config import settings
from core.database import get_session
from core.models import Course, Lab, Student, Submission
from services.storage import save_uploaded_file

logger = logging.getLogger(__name__)

router = Router()


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


@router.message(F.chat.id == settings.group_id, F.reply_to_message)
async def handle_reply(message: Message):
    replied = message.reply_to_message
    if not replied or not replied.from_user:
        return

    if replied.from_user.id != (await message.bot.me()).id:
        return

    if not message.text:
        return

    reply_text = message.text.strip()

    async with await get_session() as session:
        result = await session.execute(
            select(Submission).where(
                Submission.bot_message_id == replied.message_id,
                Submission.pending == True,
            )
        )
        submission = result.scalar_one_or_none()

        if not submission:
            await message.answer("⚠️ Нет ожидающей обработки для этого сообщения.")
            return

        ctx = dict(submission.context) if submission.context else {}

        import re

        student_match = re.search(
            r'(?:студент|студента?|фио|фамилия)\s*[:\s]\s*(.+?)(?:,|$|\n)',
            reply_text, re.IGNORECASE
        )
        if student_match:
            ctx["student_name"] = student_match.group(1).strip()

        course_match = re.search(
            r'(?:курс|предмет|дисциплин[ауы])\s*[:\s]\s*(.+?)(?:,|$|\n)',
            reply_text, re.IGNORECASE
        )
        if course_match:
            ctx["course"] = course_match.group(1).strip()

        lab_match = re.search(
            r'(?:лаб[а]?|лабораторн[аяой])\s*[:\s]\s*(.+?)(?:,|$|\n)',
            reply_text, re.IGNORECASE
        )
        if lab_match:
            ctx["lab"] = lab_match.group(1).strip()

        course_guess = ctx.get("course") or ctx.get("course_guess")
        lab_guess = ctx.get("lab") or ctx.get("lab_guess")
        student_name = ctx.get("student_name")

        if not (course_guess and lab_guess and student_name):
            submission.context = ctx
            await session.commit()

            missing = [m for m, v in [("студент", student_name), ("курс", course_guess), ("лаба", lab_guess)] if not v]
            await message.answer(
                f"⚠️ Всё ещё не хватает: {', '.join(missing)}.\n"
                f"Уточните, пожалуйста."
            )
            return

        course = await create_or_get_course(session, course_guess)
        lab = await create_or_get_lab(session, course.id, lab_guess)
        student = await create_or_get_student(session, student_name)

        submission.lab_id = lab.id
        submission.student_id = student.id
        submission.pending = False
        submission.context = ctx
        await session.commit()

    await message.answer(
        f"✅ <b>Работа сохранена!</b>\n"
        f"{course_guess} → {lab_guess} → {student_name}"
    )
