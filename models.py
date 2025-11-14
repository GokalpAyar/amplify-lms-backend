# models.py
# ==========================================================
# SQLModel database models for Amplify-LMS
# Supports authentication + ownership (User ↔ Assignment)
# Compatible with FastAPI + SQLAlchemy + Pydantic v2
# ==========================================================

from sqlmodel import SQLModel, Field, Column, JSON, Relationship
from datetime import datetime
from typing import List, Optional
import uuid


# ---------------------- User Model ----------------------
class User(SQLModel, table=True):
    """
    Instructor or student user model.
    For now, only instructors are supported for authentication and assignment ownership.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str
    email: str
    password_hash: str
    role: str = "teacher"  # 'teacher' or 'student' (future use)

    # Relationship: one instructor → many assignments
    assignments: List["Assignment"] = Relationship(back_populates="owner")

    model_config = {"arbitrary_types_allowed": True}


# ---------------------- Assignment Model ----------------------
class Assignment(SQLModel, table=True):
    """
    Stores teacher-created assignments with metadata and questions.
    Each assignment belongs to an instructor (owner_id).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    title: str
    description: Optional[str] = None
    dueDate: Optional[str] = None
    isQuiz: bool = False
    assignmentTimeLimit: Optional[int] = None  # in seconds (for quizzes/tests)

    # Full question data (JSON)
    questions: dict = Field(sa_column=Column(JSON))

    # Relationship to the instructor (owner)
    owner_id: Optional[str] = Field(default=None, foreign_key="user.id")
    owner: Optional[User] = Relationship(back_populates="assignments")

    # Relationship to student responses
    responses: List["Response"] = Relationship(back_populates="assignment")

    model_config = {"arbitrary_types_allowed": True}


# ---------------------- Response Model ----------------------
class Response(SQLModel, table=True):
    """
    Stores each student’s submission and grading info.
    Linked to Assignment for instructor-level filtering.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    assignment_id: str = Field(foreign_key="assignment.id")
    studentName: str
    jNumber: str

    # Store answers and transcripts as JSON
    answers: dict = Field(sa_column=Column(JSON))
    transcripts: dict = Field(sa_column=Column(JSON))

    submittedAt: datetime = Field(default_factory=datetime.utcnow)
    grade: Optional[float] = None  # optional instructor-assigned grade

    # Relationship back to Assignment
    assignment: Optional[Assignment] = Relationship(back_populates="responses")

    model_config = {"arbitrary_types_allowed": True}
