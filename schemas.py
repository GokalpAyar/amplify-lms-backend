# schemas.py
from pydantic import BaseModel
from typing import Any, Dict
from datetime import datetime

# ---------- Assignment Schemas ----------

class AssignmentCreate(BaseModel):
    title: str
    description: str | None = None
    dueDate: str | None = None
    isQuiz: bool = False
    questions: Dict[str, Any] | list


class AssignmentOut(AssignmentCreate):
    id: str

    class Config:
        orm_mode = True   # allows direct DB-to-JSON conversion


# ---------- Response Schemas ----------

class ResponseCreate(BaseModel):
    assignment_id: str
    studentName: str
    jNumber: str
    answers: Dict[str, Any]
    transcripts: Dict[str, Any]


class ResponseOut(ResponseCreate):
    id: str
    submittedAt: datetime   # changed from str → datetime
    grade: float | None = None

    class Config:
        orm_mode = True     # FastAPI auto-serializes datetime

