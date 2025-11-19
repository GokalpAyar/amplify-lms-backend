# routes/responses.py

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from db import get_session
from models import Assignment, Response
from schemas import ResponseCreate, ResponseOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/responses", tags=["responses"])


@router.post("/", response_model=ResponseOut)
def create_response(
    payload: ResponseCreate,
    session: Session = Depends(get_session),
):
    """Create a new student response (no authentication required for students)."""

    try:
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
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception(
            "Failed to store submission for assignment %s",
            payload.assignment_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to store response right now.",
        ) from exc


@router.get("/")
def list_responses(
    owner_id: str | None = Query(
        default=None,
        description="Optionally filter responses by assignment owner_id.",
    ),
    session: Session = Depends(get_session),
):
    """List responses, optionally filtering by instructor owner_id (demo mode)."""

    stmt = select(Response)

    if owner_id:
        assignment_ids = [
            assignment.id
            for assignment in session.exec(
                select(Assignment).where(Assignment.owner_id == owner_id)
            ).all()
        ]

        if not assignment_ids:
            return []

        stmt = stmt.where(Response.assignment_id.in_(assignment_ids))

    return session.exec(stmt).all()


@router.get("/{assignment_id}")
def get_responses_for_assignment(
    assignment_id: str,
    session: Session = Depends(get_session),
):
    """Get responses for a specific assignment (no authentication required)."""

    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    responses = session.exec(
        select(Response).where(Response.assignment_id == assignment_id)
    ).all()

    return responses