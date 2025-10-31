# models.py
# ==========================================================
# SQLModel database models for Amplify-LMS
# Compatible with FastAPI + SQLAlchemy + Pydantic v2
# ==========================================================

from sqlmodel import SQLModel, Field, Column, JSON
from datetime import datetime
import uuid


# ---------------------- Assignment Model ----------------------
class Assignment(SQLModel, table=True):
    """Stores teacher-created assignments with metadata and questions."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    title: str
    description: str | None = None
    dueDate: str | None = None
    isQuiz: bool = False

    # Store full question data (JSON)
    questions: dict = Field(sa_column=Column(JSON))

    # ✅ Fix for Pydantic v2 + SQLAlchemy JSON compatibility
    model_config = {"arbitrary_types_allowed": True}


# ---------------------- Response Model ----------------------
class Response(SQLModel, table=True):
    """Stores each student’s submission and grading info."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    assignment_id: str
    studentName: str
    jNumber: str

    # Store answers and transcripts as JSON
    answers: dict = Field(sa_column=Column(JSON))
    transcripts: dict = Field(sa_column=Column(JSON))

    submittedAt: datetime = Field(default_factory=datetime.utcnow)
    grade: float | None = None  # optional instructor-assigned grade

    # ✅ Required fix for JSON field schema generation
    model_config = {"arbitrary_types_allowed": True}




