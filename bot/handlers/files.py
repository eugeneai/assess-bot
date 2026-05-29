import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select

from core.config import settings
from core.database import get_session
from core.models import Course, Lab, Student, Submission
from services.parser import extract_text_from_file, extract_zip
from services.storage import save_uploaded_file
from services.context import ContextDetector
from services.student_id import extract_student_name, extract_group

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


async def _process_work_group(
    message: Message,
    group: dict,
    forward_chat_name: str | None,
    raw_text: str,
    bot_msg: Message | None,
):
    extracted_text = ""
    all_texts = []

    for f in group.get("files", []):
        text = await extract_text_from_file(f["path"], f["name"])
        if text:
            all_texts.append(text)

    extracted_text = "\n".join(all_texts)

    ctx = await context_detector.analyze(
        forward_chat_name=forward_chat_name,
        message_text=raw_text,
        extracted_text=extracted_text,
    )

    student_name = group.get("student_name") or extract_student_name(extracted_text) or ctx.get("student_name")
    course_guess = ctx.get("course")
    lab_guess = ctx.get("lab")
    group_name = extract_group(extracted_text) or ctx.get("group", "")
    confidence = ctx.get("confidence", 0)
    needs_clarification = ctx.get("needs_clarification", False)

    files_meta = [
        {
            "file_id": "",
            "file_name": f["name"],
            "file_path": f["path"],
            "file_size": 0,
        }
        for f in group.get("files", [])
    ]

    if student_name and course_guess and lab_guess:
        async with await get_session() as session:
            course = await create_or_get_course(session, course_guess)
            lab = await create_or_get_lab(session, course.id, lab_guess)
            student = await create_or_get_student(session, student_name)
            if group_name and not student.group_name:
                student.group_name = group_name
                await session.commit()

            submission = Submission(
                lab_id=lab.id,
                student_id=student.id,
                pending=False,
                forwarded_message_id=message.message_id,
                forwarded_chat_id=message.chat.id,
                bot_message_id=bot_msg.message_id if bot_msg else None,
                raw_text=raw_text,
                files_meta=files_meta,
                extracted_text=extracted_text,
                context=ctx,
                forwarded_at=datetime.utcnow(),
            )
            session.add(submission)
            await session.commit()
            return f"{student.full_name} → {course.title} → {lab.title}"

    return None


@router.message(F.chat.id == settings.group_id, F.forward_origin)
async def handle_forwarded(message: Message):
    if not message.forward_origin:
        return

    await message.answer("⏳ Анализирую полученную работу...")

    forward_chat_name = None
    fo = message.forward_origin
    if hasattr(fo, 'chat') and fo.chat:
        forward_chat_name = fo.chat.title
    if hasattr(fo, 'sender_chat') and fo.sender_chat:
        forward_chat_name = fo.sender_chat.title

    raw_text = message.text or message.caption or ""
    saved_results = []
    needs_clarification = False

    if message.document and message.document.file_name and message.document.file_name.lower().endswith(".zip"):
        zip_path = await save_uploaded_file(message.bot, message.document)
        groups = extract_zip(zip_path, message.document.file_name)

        if not groups:
            await message.answer("⚠️ Не удалось распаковать ZIP или в нём нет документов.")
            return

        await message.answer(f"📦 Найдено {len(groups)} групп файлов в архиве.")

        for i, group in enumerate(groups):
            bot_msg = await message.answer(f"⏳ Обрабатываю группу {i+1}/{len(groups)}: {group.get('group_name', '...')}")
            result = await _process_work_group(
                message, group, forward_chat_name, raw_text, bot_msg
            )
            if result:
                saved_results.append(result)
                await message.answer(f"✅ {result}")
            else:
                needs_clarification = True
                await message.answer(
                    f"⚠️ Не удалось определить контекст для группы «{group.get('group_name', '?')}».\n"
                    f"Ответьте на это сообщение с уточнением."
                )

        if saved_results:
            await message.answer(f"✅ Всего сохранено: {len(saved_results)} работ")

    else:
        if message.document:
            file_path = await save_uploaded_file(message.bot, message.document)
            files_meta = [{
                "file_id": message.document.file_id,
                "file_name": message.document.file_name,
                "file_path": file_path,
                "file_size": message.document.file_size,
                "mime_type": message.document.mime_type,
            }]
            extracted_text = (await extract_text_from_file(file_path, message.document.file_name or "")) or ""
        else:
            files_meta = []
            extracted_text = ""

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
        needs = ctx.get("needs_clarification", False)

        summary = (
            f"📥 <b>Получена работа</b>\n\n"
            f"👤 <b>Студент:</b> {student_name or '❓ Не определён'}\n"
            f"📚 <b>Курс:</b> {course_guess or '❓ Не определён'}\n"
            f"🔬 <b>Лаба:</b> {lab_guess or '❓ Не определён'}\n\n"
            f"📊 Уверенность: {int(confidence * 100)}%"
        )

        if not needs and student_name and course_guess and lab_guess:
            bot_msg = await message.answer(f"{summary}\n\n✅ <b>Работа сохранена:</b>")
            async with await get_session() as session:
                course = await create_or_get_course(session, course_guess)
                lab = await create_or_get_lab(session, course.id, lab_guess)
                student = await create_or_get_student(session, student_name)
                group_name = extract_group(extracted_text) or ctx.get("group", "")
                if group_name and not student.group_name:
                    student.group_name = group_name
                    await session.commit()

                submission = Submission(
                    lab_id=lab.id, student_id=student.id, pending=False,
                    forwarded_message_id=message.message_id,
                    forwarded_chat_id=message.chat.id,
                    bot_message_id=bot_msg.message_id,
                    raw_text=raw_text, files_meta=files_meta,
                    extracted_text=extracted_text, context=ctx,
                    forwarded_at=datetime.utcnow(),
                )
                session.add(submission)
                await session.commit()
        else:
            bot_msg = await message.answer(
                f"{summary}\n\n⚠️ <b>Нужно уточнение.</b>\n"
                f"Ответьте на это сообщение, указав недостающие данные."
            )
            async with await get_session() as session:
                session.add(Submission(
                    pending=True,
                    forwarded_message_id=message.message_id,
                    forwarded_chat_id=message.chat.id,
                    bot_message_id=bot_msg.message_id,
                    raw_text=raw_text, files_meta=files_meta,
                    extracted_text=extracted_text, context=ctx,
                ))
                await session.commit()
