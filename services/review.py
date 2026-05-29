import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import settings


def slugify(text: str, max_len: int = 50) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\sа-яёa-z-]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')[:max_len].rstrip('-')


def organize_files(files_meta: list[dict], course_slug: str, lab_slug: str, student_slug: str) -> list[dict]:
    dest_dir = Path(settings.storage_path) / course_slug / lab_slug / student_slug
    dest_dir.mkdir(parents=True, exist_ok=True)

    updated = []
    for fm in files_meta:
        src = fm.get("file_path", "")
        if src and os.path.isfile(src):
            prefix = datetime.utcnow().strftime("%Y-%m-%d")
            fname = fm.get("file_name", "file")
            dst = dest_dir / f"{prefix}__{fname}"
            try:
                shutil.copy2(src, str(dst))
                fm["file_path"] = str(dst)
            except OSError:
                pass
        updated.append(fm)
    return updated


def generate_review(
    student_name: str,
    course_title: str,
    lab_title: str,
    grade: int | None,
    feedback: str,
    files_meta: list[dict],
    graded_at: datetime | None = None,
    extracted_text: str = "",
) -> str:
    lines = [
        "# Рецензия на лабораторную работу\n",
        f"**Студент:** {student_name}",
        f"**Курс:** {course_title}",
        f"**Лабораторная:** {lab_title}",
        f"**Дата проверки:** {(graded_at or datetime.utcnow()).strftime('%d.%m.%Y %H:%M')}\n",
    ]

    if grade is not None:
        lines.append("## Оценка\n")
        lines.append(f"**{grade}/100**\n")

    if feedback:
        lines.append("## Комментарий преподавателя\n")
        lines.append(f"{feedback}\n")

    if files_meta:
        lines.append("## Файлы работы\n")
        for f in files_meta:
            name = f.get("file_name", "файл")
            size = f.get("file_size", 0)
            lines.append(f"- {name} ({_fmt_size(size)})")
        lines.append("")

    if extracted_text:
        lines.append("## Содержание отчёта\n")
        preview = extracted_text.strip()[:500]
        lines.append(f"```\n{preview}\n```\n")
        if len(extracted_text) > 500:
            lines.append("*...текст сокращён*")

    lines.append("\n---\n")
    lines.append("*Рецензия сгенерирована автоматически.*")

    return "\n".join(lines)


def write_review(dest_dir: str, content: str):
    path = Path(dest_dir) / "REVIEW.md"
    path.write_text(content, encoding="utf-8")


GLOBAL_PROMPT_NAME = "PROMPT.md"


def load_prompt(file_path: str) -> str | None:
    path = Path(file_path)
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return None


def save_prompt(file_path: str, content: str):
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def global_prompt_path() -> str:
    return str(Path(settings.storage_path) / GLOBAL_PROMPT_NAME)


def course_prompt_path(course_slug: str) -> str:
    return str(Path(settings.storage_path) / course_slug / GLOBAL_PROMPT_NAME)


def _fmt_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 ** 2:.1f} MB"
