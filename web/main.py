from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette import status

from core.config import settings
from core.database import get_session
from core.models import Submission, Lab, Course, Student
from services.review import generate_review, organize_files, slugify, write_review
from web.auth import verify_password

app = FastAPI(title="Assess Bot Dashboard")
templates = Jinja2Templates(directory="web/templates")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, auth=Depends(verify_password)):
    async with await get_session() as session:
        result = await session.execute(
            select(Submission).order_by(Submission.forwarded_at.desc()).limit(100)
        )
        submissions = result.scalars().all()

        rows = []
        for sub in submissions:
            lab = await session.get(Lab, sub.lab_id) if sub.lab_id else None
            student = await session.get(Student, sub.student_id) if sub.student_id else None
            course = await session.get(Course, lab.course_id) if lab and lab.course_id else None

            rows.append({
                "id": sub.id,
                "student": student.full_name if student else "—",
                "course": course.title if course else "—",
                "lab": lab.title if lab else "—",
                "grade": sub.grade,
                "feedback": sub.feedback or "",
                "files": sub.files_meta or [],
                "date": sub.forwarded_at.strftime("%d.%m.%Y %H:%M") if sub.forwarded_at else "—",
                "graded": sub.grade is not None,
            })

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "submissions": rows},
    )


@app.post("/grade/{submission_id}")
async def set_grade(
    submission_id: int,
    grade: int = Form(...),
    feedback: str = Form(""),
    auth=Depends(verify_password),
):
    if grade < 0 or grade > 100:
        raise HTTPException(status_code=400, detail="Grade must be 0-100")

    async with await get_session() as session:
        sub = await session.get(Submission, submission_id)
        if not sub:
            raise HTTPException(status_code=404, detail="Submission not found")

        sub.grade = grade
        sub.feedback = feedback
        sub.graded_by = "teacher (web)"
        from datetime import datetime
        sub.graded_at = datetime.utcnow()
        await session.commit()

        lab = await session.get(Lab, sub.lab_id) if sub.lab_id else None
        student = await session.get(Student, sub.student_id) if sub.student_id else None
        course = await session.get(Course, lab.course_id) if lab and lab.course_id else None

    if all([student, course, lab]):
        try:
            course_slug = slugify(course.title)
            lab_slug = slugify(lab.title)
            student_slug = slugify(student.full_name)
            files_meta = organize_files(sub.files_meta, course_slug, lab_slug, student_slug)

            dest_dir = f"{settings.storage_path}/{course_slug}/{lab_slug}/{student_slug}"
            content = generate_review(
                student_name=student.full_name,
                course_title=course.title,
                lab_title=lab.title,
                grade=grade,
                feedback=feedback,
                files_meta=files_meta,
                graded_at=datetime.utcnow(),
                extracted_text=sub.extracted_text or "",
            )
            write_review(dest_dir, content)

            async with await get_session() as session:
                s = await session.get(Submission, submission_id)
                s.files_meta = files_meta
                await session.commit()
        except Exception as e:
            pass

    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
