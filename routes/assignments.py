# routes/assignments.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from db import get_session
from models import Assignment
from schemas import AssignmentCreate, AssignmentOut

router = APIRouter(prefix="/assignments", tags=["assignments"])

@router.post("/", response_model=AssignmentOut)
def create_assignment(payload: AssignmentCreate, session: Session = Depends(get_session)):
    a = Assignment(**payload.dict())
    session.add(a)
    session.commit()
    session.refresh(a)
    return a

@router.get("/{assignment_id}", response_model=AssignmentOut)
def get_assignment(assignment_id: str, session: Session = Depends(get_session)):
    a = session.get(Assignment, assignment_id)
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return a

@router.get("/", response_model=list[AssignmentOut])
def list_assignments(session: Session = Depends(get_session)):
    return session.exec(select(Assignment)).all()
