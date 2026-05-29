import re

STUDENT_PATTERNS = [
    r'(?:Студент(?:ка)?|Выполнил|Работу\s+выполнил)\s*[:\s]\s*([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)',
    r'(?:ФИО|Ф\.?И\.?О\.?)\s*[:\s]\s*([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)',
    r'(?:Группа\s*:\s*\S+\s+)?([А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.[А-ЯЁ]\.)',
    r'Проверил\s*[:\s]\s*.+?\n\s*([А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.[А-ЯЁ]\.)',
    r'Работ[уа]\s+сдал\s*[:\s]\s*([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)',
]

FULL_NAME_PATTERN = r'^([А-ЯЁ][а-яё]+)\s+([А-ЯЁ][а-яё]+)(?:\s+([А-ЯЁ][а-яё]+))?$'

INITIALS_PATTERN = r'^([А-ЯЁ][а-яё]+)\s+([А-ЯЁ]\.)([А-ЯЁ]\.)?$'

TITLE_FIRST_LINE = r'^([А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.[А-ЯЁ]\.)'


def extract_student_name(text: str) -> str | None:
    if not text:
        return None

    for pattern in STUDENT_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:30]:
        match = re.match(FULL_NAME_PATTERN, line)
        if match:
            parts = [p for p in match.groups() if p]
            if len(parts) >= 2:
                return " ".join(parts)

    return None


def extract_group(text: str) -> str | None:
    patterns = [
        r'групп[аы]\s*:?\s*([А-ЯA-Z]{2,8}[-–]\d{2})',
        r'(?:студент|студентка)\s+групп[аы]\s+(\S+)',
    ]
    for pat in patterns:
        match = re.search(pat, text[:500], re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None
