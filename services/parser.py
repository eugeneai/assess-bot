import logging

logger = logging.getLogger(__name__)


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
    loop = __import__("asyncio").get_event_loop()
    return await loop.run_in_executor(None, _read_txt, file_path)


def _read_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()
