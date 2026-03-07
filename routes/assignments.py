# models.py
# ==========================================================
# SQLModel database models for Amplify-LMS
# Supports authentication + ownership
# Compatible with FastAPI + SQLAlchemy + Pydantic v2
# ==========================================================

from sqlmodel import SQLModel, Field, Column, JSON, Relationship
from sqlalchemy import ForeignKey, String, Text
from datetime import datetime
from typing import List, Optional
import uuid
from pydantic import BaseModel


# ---------------------- Pydantic Models for API ----------------------
class UserCreate(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    role: str


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


# ---------------------- User Model ----------------------
class User(SQLModel, table=True):
    """
    Legacy/local user table.
    Supabase auth is used for instructor authentication now.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: str = "instructor"
    name: Optional[str] = None

    model_config = {"arbitrary_types_allowed": True}


# ---------------------- Assignment Model ----------------------
class Assignment(SQLModel, table=True):
    """
    Stores teacher-created assignments with metadata and questions.
    owner_id stores the Supabase user id directly.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    title: str
    description: Optional[str] = None
    dueDate: Optional[str] = None
    isQuiz: bool = False
    assignmentTimeLimit: Optional[int] = None

    # frontend sends questions as a list
    questions: dict | list = Field(sa_column=Column(JSON))

    # IMPORTANT:
    # store Supabase user id directly, no foreign key to local user table
    owner_id: Optional[str] = Field(default=None, index=True)

    responses: List["Response"] = Relationship(
        back_populates="assignment",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
    )

    model_config = {"arbitrary_types_allowed": True}


# ---------------------- Assignment Draft Model ----------------------
class AssignmentDraft(SQLModel, table=True):
    """
    Stores in-progress assignments so instructors don't lose work mid-creation.
    owner_id stores the Supabase user id directly.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    title: Optional[str] = None
    description: Optional[str] = None
    questions: dict | list | None = Field(default=None, sa_column=Column(JSON))

    # IMPORTANT:
    # store Supabase user id directly, no foreign key to local user table
    owner_id: str = Field(index=True)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"arbitrary_types_allowed": True}


# ---------------------- Response Model ----------------------
class Response(SQLModel, table=True):
    """
    Stores each student's submission and grading info.
    Linked to Assignment for instructor-level filtering.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    assignment_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("assignment.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )

    studentName: str
    jNumber: str

    answers: dict = Field(sa_column=Column(JSON))
    transcripts: dict = Field(sa_column=Column(JSON))
    audio_file_url: Optional[str] = None

    student_accuracy_rating: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
        description="Student provided rating (1-5) for transcript accuracy.",
    )

    student_rating_comment: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        description="Optional student comment about transcript accuracy.",
    )

    submittedAt: datetime = Field(default_factory=datetime.utcnow)
    grade: Optional[float] = None

    assignment: Optional[Assignment] = Relationship(
        back_populates="responses",
        sa_relationship_kwargs={"passive_deletes": True},
    )

    model_config = {"arbitrary_types_allowed": True}


# ---------------------- Response Accuracy Rating ----------------------
class AccuracyRating(SQLModel, table=True):
    """
    Stores transcription accuracy reviews keyed by response.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    response_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("response.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
    )

    rating: int = Field(default=5, ge=1, le=5)
    bias_notes: Optional[str] = None
    needs_review: bool = Field(default=False)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"arbitrary_types_allowed": True}