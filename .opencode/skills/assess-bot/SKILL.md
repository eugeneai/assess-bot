---
name: assess-bot
description: >
  Assess-bot lab submission review system. Use when the user mentions
  assess-bot, grading, submissions, lab review, or student works.
---

# Assess-bot

A system for reviewing and grading student lab works. Submissions arrive via a Telegram bot
on the server and are stored in an SQLite database. The `chat-review` agent provides
a conversational interface for reviewing submissions, discussing grades, and recording
decisions locally before syncing back to the server.

## Key files

- `assess.db` — main database
- `files/PROMPT.md` — global assessment criteria
- `files/{course_slug}/PROMPT.md` — course-specific criteria
- `output/grades.jsonl` — pending grades (local)
- `output/reviews/*.md` — generated reviews (local)

## Commands

- `pull_context` — sync from server
- `push_grades` — sync to server
- `status` — show overview
- `grade <id> <score> [feedback]` — record a grade
- `review <id>` — show submission details
