import os
import re
import uuid
from pathlib import Path

from aiogram import Bot
from aiogram.types import Document

from core.config import settings


def slugify(text: str, max_len: int = 50) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\sа-яёa-z-]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')[:max_len].rstrip('-')


async def save_uploaded_file(bot: Bot, document: Document) -> str:
    storage_dir = Path(settings.storage_path) / "incoming"
    storage_dir.mkdir(parents=True, exist_ok=True)

    ext = ""
    if document.file_name and "." in document.file_name:
        ext = "." + document.file_name.rsplit(".", 1)[1]

    file_name = f"{uuid.uuid4().hex}{ext}"
    file_path = str(storage_dir / file_name)

    await bot.download(document, destination=file_path)
    return file_path


def ensure_course_lab_dir(course_slug: str, lab_slug: str, student_slug: str) -> str:
    path = Path(settings.storage_path) / course_slug / lab_slug / student_slug
    path.mkdir(parents=True, exist_ok=True)
    return str(path)
