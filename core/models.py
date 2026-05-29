from datetime import datetime

from sqlalchemy import Boolean, Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from core.database import Base


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    labs = relationship("Lab", back_populates="course", cascade="all, delete-orphan")


class Lab(Base):
    __tablename__ = "labs"

    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    title = Column(String(255), nullable=False)
    number = Column(Integer, nullable=True)
    description = Column(Text, default="")
    deadline = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    course = relationship("Course", back_populates="labs")
    submissions = relationship("Submission", back_populates="lab", cascade="all, delete-orphan")


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True)
    full_name = Column(String(255), nullable=False)
    group_name = Column(String(255), default="")
    telegram_id = Column(Integer, nullable=True, unique=True)
    telegram_username = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    submissions = relationship("Submission", back_populates="student", cascade="all, delete-orphan")


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True)
    lab_id = Column(Integer, ForeignKey("labs.id"), nullable=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=True)

    pending = Column(Boolean, default=True)
    awaiting_grade = Column(Boolean, default=False)

    forwarded_message_id = Column(Integer, nullable=True)
    forwarded_chat_id = Column(Integer, nullable=True)
    bot_message_id = Column(Integer, nullable=True)

    raw_text = Column(Text, default="")
    files_meta = Column(JSON, default=list)
    extracted_text = Column(Text, default="")
    context = Column(JSON, default=dict)

    grade = Column(Integer, nullable=True)
    feedback = Column(Text, default="")
    review = Column(Text, default="")
    graded_by = Column(String(255), default="")
    forwarded_at = Column(DateTime, default=datetime.utcnow)
    graded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    lab = relationship("Lab", back_populates="submissions")
    student = relationship("Student", back_populates="submissions")
