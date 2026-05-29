import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from core.config import settings
from core.database import get_session
from core.models import Submission, Lab, Course, Student
from services.agent import AssessmentAgent
from services.review import (
    generate_review, global_prompt_path, course_prompt_path,
    load_prompt, organize_files, save_prompt, slugify, write_review,
)

logger = logging.getLogger(__name__)

router = Router()
agent = AssessmentAgent()


@router.message(F.chat.id == settings.group_id, Command("review"))
async def cmd_review(message: Message):
    async with await get_session() as session:
        result = await session.execute(
            select(Submission)
            .where(Submission.grade.is_(None), Submission.student_id > 0)
            .order_by(Submission.forwarded_at.desc())
        )
        submissions = result.scalars().all()

    if not submissions:
        await message.answer("✅ Все работы проверены!")
        return

    for sub in submissions:
        async with await get_session() as session:
            lab = await session.get(Lab, sub.lab_id)
            student = await session.get(Student, sub.student_id)
            course = await session.get(Course, lab.course_id) if lab else None

        course_title = course.title if course else "?"
        lab_title = lab.title if lab else "?"
        student_name = student.full_name if student else "?"
        course_slug = slugify(course_title) if course else None

        suggested = await agent.suggest(sub.extracted_text, course_slug=course_slug)

        kb = InlineKeyboardBuilder()
        kb.button(text="✏️ Поставить оценку", callback_data=f"grade_{sub.id}")
        kb.button(text="📎 Файлы", callback_data=f"files_{sub.id}")
        kb.adjust(1)

        text = (
            f"📋 <b>Работа #{sub.id}</b>\n"
            f"👤 {student_name}\n"
            f"📚 {course_title} → {lab_title}\n"
            f"📅 {sub.forwarded_at.strftime('%d.%m.%Y %H:%M') if sub.forwarded_at else '?'}\n"
        )
        if suggested:
            text += f"\n🤖 <b>Предполагаемая оценка:</b> {suggested['grade']}/100"
            if suggested.get("reasoning"):
                text += f"\n💡 <i>{suggested['reasoning'][:200]}</i>"

        await message.answer(text, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("grade_"))
async def grade_callback(callback: CallbackQuery):
    sub_id = int(callback.data.split("_")[1])
    async with await get_session() as session:
        submission = await session.get(Submission, sub_id)
        if not submission:
            await callback.answer("Работа не найдена", show_alert=True)
            return

        lab = await session.get(Lab, submission.lab_id)
        student = await session.get(Student, submission.student_id)
        course = await session.get(Course, lab.course_id) if lab else None

    await callback.message.answer(
        f"✏️ <b>Оценка работы #{sub_id}</b>\n"
        f"{student.full_name if student else '?'} | "
        f"{course.title if course else '?'} → {lab.title if lab else '?'}\n\n"
        f"Введите оценку и комментарий в формате:\n"
        f"<code>85 Отличная работа, но не хватает выводов</code>\n\n"
        f"Или только число: <code>85</code>",
    )

    async with await get_session() as session:
        submission = await session.get(Submission, sub_id)
        submission.awaiting_grade = True
        await session.commit()

    await callback.answer()


@router.callback_query(F.data.startswith("files_"))
async def files_callback(callback: CallbackQuery):
    sub_id = int(callback.data.split("_")[1])
    async with await get_session() as session:
        submission = await session.get(Submission, sub_id)

    if not submission or not submission.files_meta:
        await callback.answer("Файлы не найдены", show_alert=True)
        return

    text = "📎 <b>Файлы работы:</b>\n"
    for f in submission.files_meta:
        text += f"• {f.get('file_name', 'файл')} ({f.get('file_size', 0)} bytes)\n"

    await callback.message.answer(text)
    await callback.answer()


@router.message(F.chat.id == settings.group_id, F.text)
async def handle_grade_input(message: Message):
    async with await get_session() as session:
        result = await session.execute(
            select(Submission).where(
                Submission.awaiting_grade == True,
                Submission.grade.is_(None),
            ).order_by(Submission.forwarded_at.desc()).limit(1)
        )
        submission = result.scalar_one_or_none()

    if not submission:
        return

    text = message.text.strip()
    parts = text.split(" ", 1)
    try:
        grade = int(parts[0])
        if grade < 0 or grade > 100:
            await message.answer("⚠️ Оценка должна быть от 0 до 100.")
            return
    except ValueError:
        await message.answer("⚠️ Начните с числа (оценка от 0 до 100).")
        return

    feedback = parts[1].strip() if len(parts) > 1 else ""

    async with await get_session() as session:
        submission = await session.get(Submission, submission.id)
        submission.grade = grade
        submission.feedback = feedback
        submission.graded_by = "teacher"
        submission.graded_at = datetime.utcnow()
        submission.awaiting_grade = False
        await session.commit()

        lab = await session.get(Lab, submission.lab_id)
        student = await session.get(Student, submission.student_id)
        course = await session.get(Course, lab.course_id) if lab else None

    student_name = student.full_name if student else "?"
    course_title = course.title if course else "?"
    lab_title = lab.title if lab else "?"

    await message.answer(
        f"✅ <b>Оценка сохранена!</b>\n"
        f"#{submission.id} {student_name}\n"
        f"📊 <b>{grade}/100</b>\n"
        f"{'💬 ' + feedback if feedback else ''}"
    )

    await agent.train(submission.id, grade, feedback)

    try:
        course_slug = slugify(course_title)
        lab_slug = slugify(lab_title)
        student_slug = slugify(student_name)
        files_meta = organize_files(submission.files_meta, course_slug, lab_slug, student_slug)

        dest_dir = f"{settings.storage_path}/{course_slug}/{lab_slug}/{student_slug}"
        content = generate_review(
            student_name=student_name,
            course_title=course_title,
            lab_title=lab_title,
            grade=grade,
            feedback=feedback,
            files_meta=files_meta,
            graded_at=datetime.utcnow(),
            extracted_text=submission.extracted_text or "",
        )
        write_review(dest_dir, content)

        async with await get_session() as session:
            sub = await session.get(Submission, submission.id)
            sub.files_meta = files_meta
            await session.commit()
    except Exception as e:
        logger.warning("Failed to write REVIEW.md: %s", e)


@router.message(F.chat.id == settings.group_id, Command("show_prompts"))
async def cmd_show_prompts(message: Message):
    lines = []
    gp = load_prompt(global_prompt_path())
    lines.append("🌐 <b>Глобальный промпт:</b>")
    lines.append(f"<code>{gp[:300] if gp else '— не задан'}</code>")

    async with await get_session() as session:
        result = await session.execute(select(Course))
        courses = result.scalars().all()
        for c in courses:
            cs = slugify(c.title)
            cp = load_prompt(course_prompt_path(cs))
            if cp:
                lines.append(f"\n📚 <b>{c.title}:</b>")
                lines.append(f"<code>{cp[:300]}</code>")

    await message.answer("\n".join(lines))


@router.message(F.chat.id == settings.group_id, Command("set_global_prompt"))
async def cmd_set_global_prompt(message: Message):
    if not message.reply_to_message or not message.reply_to_message.text:
        await message.answer("Ответьте (quote) на сообщение с текстом промпта.")
        return
    text = message.reply_to_message.text.strip()
    save_prompt(global_prompt_path(), text)
    await message.answer(f"✅ Глобальный промпт сохранён ({len(text)} символов).")


@router.message(F.chat.id == settings.group_id, Command("set_course_prompt"))
async def cmd_set_course_prompt(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not message.reply_to_message or not message.reply_to_message.text:
        await message.answer(
            "Формат: <code>/set_course_prompt Название курса</code>\n"
            "и ответьте (quote) на сообщение с текстом промпта."
        )
        return

    course_title = parts[1].strip()
    course_slug = slugify(course_title)
    text = message.reply_to_message.text.strip()
    save_prompt(course_prompt_path(course_slug), text)
    await message.answer(f"✅ Промпт для курса «{course_title}» сохранён ({len(text)} символов).")


@router.message(F.chat.id == settings.group_id, Command("get_course_prompt"))
async def cmd_get_course_prompt(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Формат: <code>/get_course_prompt Название курса</code>")
        return

    course_title = parts[1].strip()
    course_slug = slugify(course_title)
    cp = load_prompt(course_prompt_path(course_slug))
    if cp:
        await message.answer(f"📚 <b>{course_title}</b>\n<code>{cp[:1000]}</code>")
    else:
        await message.answer(f"Промпт для курса «{course_title}» не задан.")
