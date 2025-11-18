# routes/responses.py

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from db import get_session
from models import Assignment, Response, User
from routes.assignments import get_current_user
from schemas import ResponseCreate, ResponseOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/responses", tags=["responses"])


@router.post("/", response_model=ResponseOut)
def create_response(
    payload: ResponseCreate,
    session: Session = Depends(get_session),
):
    """Create a new student response (no authentication required for students)."""

    logger.info(
        "Received submission for assignment %s from %s",
        payload.assignment_id,
        payload.studentName,
    )

    assignment = session.get(Assignment, payload.assignment_id)
    if not assignment:
        logger.warning("Assignment not found: %s", payload.assignment_id)
        raise HTTPException(status_code=404, detail="Assignment not found")

    existing = session.exec(
        select(Response).where(
            Response.assignment_id == payload.assignment_id,
            Response.jNumber == payload.jNumber,
        )
    ).first()

    if existing:
        logger.warning("Duplicate submission detected for %s", payload.jNumber)
        raise HTTPException(
            status_code=400,
            detail="You have already submitted this assignment",
        )

    response = Response(**payload.model_dump())
    session.add(response)
    session.commit()
    session.refresh(response)

    logger.info(
        "Submission stored for assignment %s (%s)",
        payload.assignment_id,
        payload.studentName,
    )

    return response


@router.get("/")
def list_responses(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get only responses to the current instructor's assignments."""

    instructor_assignments = session.exec(
        select(Assignment).where(Assignment.owner_id == current_user.id)
    ).all()

    assignment_ids = [assignment.id for assignment in instructor_assignments]

    if not assignment_ids:
        return []

    responses = session.exec(
        select(Response).where(Response.assignment_id.in_(assignment_ids))
    ).all()

    return responses


@router.get("/{assignment_id}")
def get_responses_for_assignment(
    assignment_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get responses for a specific assignment when owned by current instructor."""

    assignment = session.get(Assignment, assignment_id)
    if not assignment or assignment.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Assignment not found")

    responses = session.exec(
        select(Response).where(Response.assignment_id == assignment_id)
    ).all()

    return responses