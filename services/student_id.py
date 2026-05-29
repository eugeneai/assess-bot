import re

PATTERNS = [
    r'(?:Студент(?:ка)?|Выполнил|Работу\s+выполнил)\s*[:\s]\s*([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)',
    r'(?:ФИО|Ф\.?И\.?О\.?)\s*[:\s]\s*([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)',
    r'(?:Группа\s*:\s*\S+\s+)?([А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.[А-ЯЁ]\.)',
]

FULL_NAME_PATTERN = r'^([А-ЯЁ][а-яё]+)\s+([А-ЯЁ][а-яё]+)(?:\s+([А-ЯЁ][а-яё]+))?$'


def extract_student_name(text: str) -> str | None:
    if not text:
        return None

    for pattern in PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()

    lines = text.split("\n")
    for line in lines[:30]:
        line = line.strip()
        match = re.match(FULL_NAME_PATTERN, line)
        if match:
            parts = [p for p in match.groups() if p]
            if len(parts) >= 2:
                return " ".join(parts)

    return None
