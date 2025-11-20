# models.py
# ==========================================================
# SQLModel database models for Amplify-LMS
# Supports authentication + ownership (User ↔ Assignment)
# Compatible with FastAPI + SQLAlchemy + Pydantic v2
# ==========================================================

from sqlmodel import SQLModel, Field, Column, JSON, Relationship
from sqlalchemy import ForeignKey, String
from datetime import datetime
from typing import List, Optional
import uuid
from pydantic import BaseModel


# ---------------------- Pydantic Models for API ----------------------
class UserCreate(BaseModel):
    """Model for user registration/login"""
    email: str
    password: str
    name: Optional[str] = None  # ← ADDED THIS LINE

class UserLogin(BaseModel):
    """Model for user login payload"""
    email: str
    password: str

class UserResponse(BaseModel):
    """Model for returning user data (without password)"""
    id: str
    email: str
    role: str

class Token(BaseModel):
    """Model for JWT token response"""
    access_token: str
    token_type: str
    user: UserResponse


# ---------------------- User Model ----------------------
class User(SQLModel, table=True):
    """
    Instructor or student user model.
    For now, only instructors are supported for authentication and assignment ownership.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: str = "instructor"  # 'instructor' or 'student' (future use)
    name: Optional[str] = None

    # Relationship: one instructor → many assignments
    assignments: List["Assignment"] = Relationship(back_populates="owner")
    drafts: List["AssignmentDraft"] = Relationship(back_populates="owner")

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
    responses: List["Response"] = Relationship(
        back_populates="assignment",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )

    model_config = {"arbitrary_types_allowed": True}


# ---------------------- Assignment Draft Model ----------------------
class AssignmentDraft(SQLModel, table=True):
    """
    Stores in-progress assignments so instructors don't lose work mid-creation.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    title: Optional[str] = None
    description: Optional[str] = None
    questions: dict | list | None = Field(default=None, sa_column=Column(JSON))

    owner_id: str = Field(foreign_key="user.id", index=True)
    owner: Optional[User] = Relationship(back_populates="drafts")

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
        index=True,
    )
    studentName: str
    jNumber: str

    # Store answers and transcripts as JSON
    answers: dict = Field(sa_column=Column(JSON))
    transcripts: dict = Field(sa_column=Column(JSON))

    submittedAt: datetime = Field(default_factory=datetime.utcnow)
    grade: Optional[float] = None  # optional instructor-assigned grade
    audio_file_url: Optional[str] = None
    audio_storage_path: Optional[str] = None
    audio_mime_type: Optional[str] = None
    audio_file_size: Optional[int] = None

    # Relationship back to Assignment
    assignment: Optional[Assignment] = Relationship(
        back_populates="responses",
        sa_relationship_kwargs={"passive_deletes": True},
    )

    model_config = {"arbitrary_types_allowed": True}