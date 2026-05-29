#!/usr/bin/env python3
"""
MCP server: assess-sync — tools for syncing and grading lab submissions.

Provides tools for opencode agents:
  - pull_context    — download DB + prompts from server
  - push_grades     — upload grades + DB changes back to server
  - status          — show ungraded submissions and local changes
  - grade           — record a grade locally
  - review          — show a submission with its review
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent

SERVER = os.environ.get("ASSESS_SERVER", "ktulhu")
REMOTE_PATH = os.environ.get("ASSESS_REMOTE_PATH", "~/projects/code/deepseek/assess-bot")
SYNC_SCRIPT = str(PROJECT / "scripts" / "sync.sh")
DB_PATH = str(PROJECT / "assess.db")
OUTPUT_DIR = PROJECT / "output" / "reviews"
GRADES_FILE = PROJECT / "output" / "grades.jsonl"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
#  DB helpers
# ═══════════════════════════════════════════════════════════════

def db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    try:
        with db_conn() as c:
            rows = c.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            return []
        raise


def execute(sql: str, params: tuple = ()):
    with db_conn() as c:
        c.execute(sql, params)
        c.commit()


def get_submission(sub_id: int) -> dict[str, Any] | None:
    rows = query(
        """SELECT s.*, st.full_name AS student_name, st.group_name,
                  l.title AS lab_title, c.title AS course_title
           FROM submissions s
           LEFT JOIN students st ON s.student_id = st.id
           LEFT JOIN labs l ON s.lab_id = l.id
           LEFT JOIN courses c ON l.course_id = c.id
           WHERE s.id = ?""",
        (sub_id,),
    )
    return rows[0] if rows else None


def get_ungraded(limit: int = 30) -> list[dict[str, Any]]:
    return query(
        """SELECT s.id, st.full_name AS student, c.title AS course,
                  l.title AS lab, s.forwarded_at, s.grade, s.feedback
           FROM submissions s
           JOIN students st ON s.student_id = st.id
           JOIN labs l ON s.lab_id = l.id
           JOIN courses c ON l.course_id = c.id
           WHERE s.grade IS NULL AND s.student_id > 0
           ORDER BY s.forwarded_at DESC LIMIT ?""",
        (limit,),
    )


def get_recent(limit: int = 30) -> list[dict[str, Any]]:
    return query(
        """SELECT s.id, st.full_name AS student, c.title AS course,
                  l.title AS lab, s.grade, s.feedback, s.graded_at,
                  substr(s.review, 1, 200) AS review_preview
           FROM submissions s
           JOIN students st ON s.student_id = st.id
           JOIN labs l ON s.lab_id = l.id
           JOIN courses c ON l.course_id = c.id
           WHERE s.student_id > 0
           ORDER BY COALESCE(s.graded_at, s.forwarded_at) DESC LIMIT ?""",
        (limit,),
    )


# ═══════════════════════════════════════════════════════════════
#  Tool implementations
# ═══════════════════════════════════════════════════════════════

def tool_pull_context(limit: int = 30) -> str:
    result = subprocess.run(
        ["bash", SYNC_SCRIPT, "pull"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        return f"❌ Sync failed:\n{result.stderr}"

    subs = get_recent(limit)
    summary_path = PROJECT / "context" / "submissions.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(subs, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    ungraded = get_ungraded()
    lines = [
        f"✅ Synced {len(subs)} submissions from {SERVER}",
        f"📁 context/submissions.json — {len(subs)} последних работ",
        f"⏳ {len(ungraded)} работ ожидают оценки",
    ]
    return "\n".join(lines)


def tool_push_grades() -> str:
    local_grades = list(GRADES_FILE.parent.glob("*.jsonl"))
    pending = 0
    for f in local_grades:
        pending += sum(1 for _ in f.open() if _.strip())

    if pending == 0:
        return "ℹ️ Нет локальных изменений для отправки."

    result = subprocess.run(
        ["bash", SYNC_SCRIPT, "push"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        return f"❌ Push failed:\n{result.stderr}"

    return f"✅ Отправлено {pending} оценок на {SERVER}"


def tool_status() -> str:
    ungraded = get_ungraded(10)
    recent = get_recent(5)

    lines = ["## 📊 Статус\n"]
    lines.append(f"**Не проверено:** {len(get_ungraded())} работ")
    if ungraded:
        lines.append("\n**Последние непроверенные:**")
        for s in ungraded:
            lines.append(f"  #{s['id']} {s['student']} — {s['course']} → {s['lab']}")

    graded_count = len([s for s in get_recent() if s["grade"] is not None])
    lines.append(f"\n**Всего проверено:** {graded_count} работ")

    lines.append("\n**Локально ожидают отправки:**")
    grades_file = GRADES_FILE
    if grades_file.exists():
        count = sum(1 for _ in grades_file.open() if _.strip())
        lines.append(f"  {count} оценок в output/grades.jsonl")
    else:
        lines.append("  нет")

    return "\n".join(lines)


def tool_grade(submission_id: int, grade_score: int, feedback: str = "") -> str:
    sub = get_submission(submission_id)
    if not sub:
        return f"❌ Работа #{submission_id} не найдена."

    if grade_score < 0 or grade_score > 100:
        return "❌ Оценка должна быть от 0 до 100."

    now = datetime.utcnow().isoformat()
    record = {
        "id": submission_id,
        "grade": grade_score,
        "feedback": feedback,
        "student": sub.get("student_name", "?"),
        "course": sub.get("course_title", "?"),
        "lab": sub.get("lab_title", "?"),
        "timestamp": now,
    }

    with open(GRADES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    student = sub.get("student_name", "?")
    course = sub.get("course_title", "?")
    lab = sub.get("lab_title", "?")

    review_path = OUTPUT_DIR / f"review_{submission_id}.md"
    review_content = (
        f"# Рецензия на работу #{submission_id}\n\n"
        f"**Студент:** {student}\n"
        f"**Курс:** {course} → {lab}\n"
        f"**Оценка:** {grade_score}/100\n"
        f"**Комментарий:** {feedback or '—'}\n"
        f"**Дата:** {now[:10]}\n"
    )
    review_path.write_text(review_content, encoding="utf-8")

    return (
        f"✅ Оценка #{submission_id}: {grade_score}/100\n"
        f"   {student} | {course} → {lab}\n"
        f"   Записано локально. Используйте push для отправки на сервер."
    )


def tool_review(submission_id: int) -> str:
    sub = get_submission(submission_id)
    if not sub:
        return f"❌ Работа #{submission_id} не найдена."

    lines = [
        f"📋 **Работа #{submission_id}**",
        f"👤 Студент: {sub.get('student_name', '?')}",
        f"📚 Курс: {sub.get('course_title', '?')} → {sub.get('lab_title', '?')}",
    ]
    if sub.get("grade") is not None:
        lines.append(f"📊 Оценка: {sub['grade']}/100")
        lines.append(f"💬 Фидбек: {sub.get('feedback', '—')}")
    else:
        lines.append("⏳ Ожидает оценки")

    if sub.get("review"):
        lines.append(f"\n📄 **Рецензия:**\n{sub['review']}")
    else:
        lok = OUTPUT_DIR / f"review_{submission_id}.md"
        if lok.exists():
            lines.append(f"\n📄 **Локальная рецензия:**\n{lok.read_text(encoding='utf-8')}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  MCP server
# ═══════════════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "pull_context",
        "description": "Скачать контекст (DB, PROMPT.md, submissions.json) с сервера. Выполнять при старте сессии.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Сколько последних работ", "default": 30}
            },
        },
    },
    {
        "name": "push_grades",
        "description": "Отправить локальные оценки и рецензии обратно на сервер.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "status",
        "description": "Показать статус: сколько не проверено, что ждёт отправки.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "grade",
        "description": "Записать оценку для работы (локально). После оценки используйте push_grades для отправки на сервер.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "submission_id": {"type": "integer", "description": "ID работы"},
                "grade_score": {"type": "integer", "description": "Оценка 0–100"},
                "feedback": {"type": "string", "description": "Комментарий (опционально)"},
            },
            "required": ["submission_id", "grade_score"],
        },
    },
    {
        "name": "review",
        "description": "Показать полную информацию и рецензию по работе.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "submission_id": {"type": "integer", "description": "ID работы"},
            },
            "required": ["submission_id"],
        },
    },
]


def handle_call(name: str, args: dict) -> str:
    handlers = {
        "pull_context": lambda: tool_pull_context(args.get("limit", 30)),
        "push_grades": tool_push_grades,
        "status": tool_status,
        "grade": lambda: tool_grade(args["submission_id"], args["grade_score"], args.get("feedback", "")),
        "review": lambda: tool_review(args["submission_id"]),
    }
    fn = handlers.get(name)
    if not fn:
        return f"❌ Unknown tool: {name}"
    try:
        return fn()
    except Exception as e:
        return f"❌ Error: {e}"


def main():
    """MCP stdio transport."""
    import sys

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_id = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params", {}) or {}

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "assess-sync", "version": "1.0.0"},
                    "capabilities": {"tools": {}},
                },
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        elif method == "notifications/initialized":
            pass

        elif method == "list_tools":
            resp = {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        elif method == "call_tool":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {}) or {}
            result = handle_call(tool_name, tool_args)
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": result}],
                    "isError": result.startswith("❌"),
                },
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        elif method == "ping":
            sys.stdout.write(
                json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {}}) + "\n"
            )
            sys.stdout.flush()


if __name__ == "__main__":
    main()
