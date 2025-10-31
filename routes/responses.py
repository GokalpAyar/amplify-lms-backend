# routes/responses.py
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from db import get_session
from models import Response
from schemas import ResponseCreate, ResponseOut

router = APIRouter(prefix="/responses", tags=["responses"])


@router.post("/", response_model=ResponseOut)
def submit_response(payload: ResponseCreate, session: Session = Depends(get_session)):
    """Save a student's assignment submission."""
    r = Response(**payload.dict())
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


@router.get("/", response_model=list[ResponseOut])
def list_responses(
    assignment_id: str | None = Query(None),
    session: Session = Depends(get_session),
):
    """
    List all responses.
    If `assignment_id` is provided, return only those responses.
    Otherwise, return all student submissions.
    """
    if assignment_id:
        stmt = select(Response).where(Response.assignment_id == assignment_id)
    else:
        stmt = select(Response)
    return session.exec(stmt).all()

@router.put("/{response_id}/grade", response_model=ResponseOut)
def update_grade(response_id: str, grade: float, session: Session = Depends(get_session)):
    """Update a student's grade for a specific submission."""
    response = session.get(Response, response_id)
    if not response:
        return {"error": "Response not found"}
    response.grade = grade
    session.add(response)
    session.commit()
    session.refresh(response)
    return response


