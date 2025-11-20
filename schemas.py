# schemas.py
# ==========================================================
# Pydantic schemas for Amplify-LMS
# Matches SQLModel models (User ↔ Assignment ↔ Response)
# ==========================================================

from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, List
from datetime import datetime


# ---------------------- User Schemas ----------------------
class UserBase(BaseModel):
    id: str
    name: Optional[str] = None
    email: str
    role: str = "teacher"

    class Config:
        orm_mode = True


# ---------------------- Assignment Schemas ----------------------
class AssignmentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    dueDate: Optional[str] = None
    isQuiz: bool = False
    assignmentTimeLimit: Optional[int] = None  # ✅ new field
    questions: Dict[str, Any] | list
    owner_id: Optional[str] = None             # ✅ new field (teacher’s ID)
    draft_id: Optional[str] = None             # Optional draft to convert on publish


class AssignmentOut(AssignmentCreate):
    id: str
    owner: Optional[UserBase] = None           # ✅ include owner info if needed

    class Config:
        orm_mode = True   # allows direct DB-to-JSON conversion


# ---------------------- Assignment Draft Schemas ----------------------
class AssignmentDraftBase(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    questions: Dict[str, Any] | list | None = None


class AssignmentDraftCreate(AssignmentDraftBase):
    owner_id: str


class AssignmentDraftUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    questions: Dict[str, Any] | list | None = None
    owner_id: Optional[str] = None


class AssignmentDraftOut(AssignmentDraftBase):
    id: str
    owner_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


# ---------------------- Response Schemas ----------------------
class ResponseCreate(BaseModel):
    assignment_id: str
    studentName: str
    jNumber: str
    answers: Dict[str, Any]
    transcripts: Dict[str, Any]
    audio_file_url: Optional[str] = None


class ResponseOut(ResponseCreate):
    id: str
    submittedAt: datetime
    grade: Optional[float] = None

    class Config:
        orm_mode = True


class AccuracyRatingPayload(BaseModel):
    rating: int = Field(ge=1, le=5)
    bias_notes: Optional[str] = None
    needs_review: bool = False


class AccuracyRatingOut(AccuracyRatingPayload):
    id: str
    response_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
