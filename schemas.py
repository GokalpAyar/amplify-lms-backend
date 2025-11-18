# schemas.py
# ==========================================================
# Pydantic schemas for Amplify-LMS
# Matches SQLModel models (User ↔ Assignment ↔ Response)
# ==========================================================

from pydantic import BaseModel
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


class AssignmentOut(AssignmentCreate):
    id: str
    owner: Optional[UserBase] = None           # ✅ include owner info if needed

    class Config:
        orm_mode = True   # allows direct DB-to-JSON conversion


# ---------------------- Response Schemas ----------------------
class ResponseCreate(BaseModel):
    assignment_id: str
    studentName: str
    jNumber: str
    answers: Dict[str, Any]
    transcripts: Dict[str, Any]


class ResponseOut(ResponseCreate):
    id: str
    submittedAt: datetime
    grade: Optional[float] = None

    class Config:
        orm_mode = True
