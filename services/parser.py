import asyncio
import logging
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any
from zipfile import ZipFile, BadZipFile

from core.config import settings

logger = logging.getLogger(__name__)

TITLE_PATTERNS: dict[str, list[str]] = {
    "practice": [
        r'(учебн[аяой]{2,3}|производственн[аяой]{2,3}|преддипломн[аяой]{2,3})\s+практик[а-я]*',
        r'практик[а-я]*\s+по\s+получени[юя]?\s+профессиональн[ы]',
        r'НИР[С]?',
    ],
    "discipline": [
        r'по\s+дисциплин[еы]\s*[«"](.+?)[»"]',
        r'дисциплин[аеы]\s*[:\s]\s*(.+?)[\n,]',
        r'(?:по\s+)?курс[уеа]?\s*[«"](.+?)[»"]',
        r'по\s+предмет[уе]?\s*[«"](.+?)[»"]',
    ],
    "group": [
        r'групп[аы]\s*:?\s*([А-ЯA-Z]{2,8}[-–]\d{2})',
        r'(?:студент|студентка)\s+групп[аы]\s+(\S+)',
    ],
    "lab_numbers": [
        r'(?:лабораторн[аяойю]+?\s+работа\s*[№#]?\s*)(\d+)',
        r'Л[Рр]\s*(\d+)',
    ],
}


async def extract_text_from_file(file_path: str, file_name: str) -> str | None:
    try:
        if file_name.lower().endswith(".pdf"):
            return await _extract_pdf(file_path)
        elif file_name.lower().endswith(".docx"):
            return await _extract_docx(file_path)
        elif file_name.lower().endswith(".txt"):
            return await _extract_txt(file_path)
        elif file_name.lower().endswith(".zip"):
            return None
        else:
            return None
    except Exception as e:
        logger.warning("Failed to extract text from %s: %s", file_name, e)
        return None


async def _extract_pdf(file_path: str) -> str:
    import pdfplumber

    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


async def _extract_docx(file_path: str) -> str:
    from docx import Document

    doc = Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


async def _extract_txt(file_path: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _read_txt, file_path)


def _read_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def extract_title_info(text: str) -> dict[str, Any]:
    info: dict[str, Any] = {
        "practice": None,
        "discipline": None,
        "course": None,
        "group": None,
        "lab_numbers": [],
    }

    if not text:
        return info

    for key, patterns in TITLE_PATTERNS.items():
        for pat in patterns:
            match = re.search(pat, text[:1000], re.IGNORECASE)
            if match:
                val = match.group(1).strip() if match.lastindex else match.group(0).strip()
                if key == "lab_numbers":
                    info["lab_numbers"].append(int(match.group(1)))
                elif key == "practice":
                    info["practice"] = match.group(0).strip().capitalize()
                elif key == "discipline":
                    info["discipline"] = val
                    info["course"] = val
                elif key == "group":
                    info["group"] = val
                break

    info["lab_numbers"] = sorted(set(info["lab_numbers"]))
    return info


def extract_zip(file_path: str, file_name: str) -> list[dict[str, Any]]:
    extract_dir = Path(settings.storage_path) / "tmp" / uuid.uuid4().hex
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        with ZipFile(file_path, "r") as zf:
            zf.extractall(str(extract_dir))
    except BadZipFile:
        logger.warning("Bad zip file: %s", file_path)
        return []
    except Exception as e:
        logger.warning("Failed to extract zip %s: %s", file_path, e)
        return []

    return _group_extracted_files(extract_dir, file_name)


def _group_extracted_files(extract_dir: Path, archive_name: str) -> list[dict[str, Any]]:
    doc_exts = {".pdf", ".docx", ".doc", ".txt"}
    code_exts = {".py", ".c", ".cpp", ".java", ".js", ".php", ".html", ".css", ".sql", ".ipynb"}
    allowed = doc_exts | code_exts

    groups: list[dict[str, Any]] = []
    entries = sorted(extract_dir.rglob("*"))

    dirs = sorted(e for e in entries if e.is_dir())
    for d in dirs:
        student_key = d.name.strip().replace("_", " ").replace(".", " ")
        student_name = _guess_student_from_dirname(student_key)
        files = []
        for f in sorted(d.rglob("*")):
            if f.is_file() and f.suffix.lower() in allowed:
                files.append({"path": str(f), "name": f.name})
        if files:
            groups.append({
                "student_name": student_name,
                "group_name": d.name,
                "files": files,
            })

    root_files = sorted(
        f for f in entries if f.is_file() and f.suffix.lower() in allowed
    )

    if dirs:
        for f in root_files:
            student_name = _guess_student_from_filename(f.stem)
            groups.append({
                "student_name": student_name,
                "group_name": f.stem,
                "files": [{"path": str(f), "name": f.name}],
            })
    else:
        files = [{"path": str(f), "name": f.name} for f in root_files]
        if files:
            archive_stem = Path(archive_name).stem
            student_name = _guess_student_from_filename(archive_stem)
            groups.append({
                "student_name": student_name,
                "group_name": archive_stem,
                "files": files,
            })

    return groups


def _guess_student_from_dirname(name: str) -> str:
    parts = name.strip().split()
    if len(parts) >= 2:
        return " ".join(parts[:3])
    return parts[0] if parts else name


def _guess_student_from_filename(stem: str) -> str:
    stem = stem.replace("_", " ").replace(".", " ")
    stem = re.sub(r'\b(?:лаб|лр|отчет|report|lab|отчёт)\s*\d*\b', '', stem, flags=re.IGNORECASE).strip()
    stem = re.sub(r'\s+', ' ', stem).strip()
    return stem
