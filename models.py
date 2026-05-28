# models.py
# ==========================================================
# SQLModel database models for Amplify-LMS
# Supports authentication + ownership
# Compatible with FastAPI + SQLAlchemy + Pydantic v2
# ==========================================================

from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel
from sqlalchemy import Column, ForeignKey, JSON, String, Text
from sqlmodel import Field, Relationship, SQLModel


# ==========================================================
# Pydantic Models for API Auth
# ==========================================================
class UserCreate(BaseModel):
    """Model for user registration/login."""
    email: str
    password: str
    name: Optional[str] = None


class UserLogin(BaseModel):
    """Model for user login payload."""
    email: str
    password: str


class UserResponse(BaseModel):
    """Model for returning user data (without password)."""
    id: str
    email: str
    role: str


class Token(BaseModel):
    """Model for JWT token response."""
    access_token: str
    token_type: str
    user: UserResponse


# ==========================================================
# Legacy Local User Model
# ==========================================================
class User(SQLModel, table=True):
    """
    Legacy/local user table.

    Supabase auth is now used for instructor authentication, but this table
    may still exist for older parts of the system.
    """

    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: str = "instructor"
    name: Optional[str] = None

    model_config = {"arbitrary_types_allowed": True}


# ==========================================================
# Assignment Model
# ==========================================================
class Assignment(SQLModel, table=True):
    """
    Stores teacher-created assignments with metadata and questions.

    IMPORTANT:
    owner_id stores the Supabase user id directly.
    It is NOT a foreign key to the local user table anymore.
    """

    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    title: str
    description: Optional[str] = None
    dueDate: Optional[str] = None
    isQuiz: bool = False
    assignmentTimeLimit: Optional[int] = None

    # Frontend sends questions as a list of question objects
    questions: dict | list = Field(sa_column=Column(JSON))

    # Store Supabase user id directly
    owner_id: Optional[str] = Field(default=None, index=True)

    responses: List["Response"] = Relationship(
        back_populates="assignment",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
    )

    model_config = {"arbitrary_types_allowed": True}


# ==========================================================
# Assignment Draft Model
# ==========================================================
class AssignmentDraft(SQLModel, table=True):
    """
    Stores in-progress assignments so instructors do not lose work mid-creation.

    IMPORTANT:
    owner_id stores the Supabase user id directly.
    It is NOT a foreign key to the local user table anymore.
    """

    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    title: Optional[str] = None
    description: Optional[str] = None
    questions: dict | list | None = Field(default=None, sa_column=Column(JSON))

    owner_id: str = Field(index=True)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"arbitrary_types_allowed": True}


# ==========================================================
# Student Response Model
# ==========================================================
class Response(SQLModel, table=True):
    """
    Stores each student's submission and grading info.
    Linked to Assignment for instructor-level filtering.
    """

    __table_args__ = {"extend_existing": True}

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

    # Store answers and transcripts as JSON
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
    grading_result: Optional["GradingResult"] = Relationship(
        back_populates="response",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "uselist": False,
            "passive_deletes": True,
        },
    )

    model_config = {"arbitrary_types_allowed": True}


# ==========================================================
# Automatic Grading Result Model
# ==========================================================
class GradingResult(SQLModel, table=True):
    """
    Stores automatic grading output for a student response.

    Instructor-approved final grades stay on Response.grade.
    """

    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    response_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("response.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
    )

    status: str = Field(default="pending", index=True)
    total_score: Optional[float] = None
    max_score: Optional[float] = None
    percentage: Optional[float] = None

    question_results: dict | list = Field(default_factory=list, sa_column=Column(JSON))
    summary_feedback: Optional[str] = Field(default=None, sa_column=Column(Text))
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    grader_version: Optional[str] = None
    instructor_feedback: Optional[str] = Field(default=None, sa_column=Column(Text))
    regrade_reason: Optional[str] = Field(default=None, sa_column=Column(Text))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    regraded_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    approved_score: Optional[float] = None
    approved_by: Optional[str] = None

    response: Optional[Response] = Relationship(back_populates="grading_result")

    model_config = {"arbitrary_types_allowed": True}


# ==========================================================
# Response Accuracy Rating Model
# ==========================================================
class AccuracyRating(SQLModel, table=True):
    """
    Stores transcription accuracy reviews keyed by response.
    """

    __table_args__ = {"extend_existing": True}

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
