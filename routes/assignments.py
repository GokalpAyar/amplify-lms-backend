# routes/assignments.py
# ==========================================================
# Routes for creating and retrieving assignments.
# Demo mode removes JWT requirements for easier testing.
# ==========================================================

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from db import get_session
from models import Assignment, Response
from schemas import AssignmentCreate, AssignmentOut

# ----------------------------------------------------------
# Router setup
# ----------------------------------------------------------
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assignments", tags=["assignments"])

# ----------------------------------------------------------
# POST /assignments/
# Instructor creates new assignment
# ----------------------------------------------------------
@router.post("/", response_model=AssignmentOut)
def create_assignment(
    payload: AssignmentCreate,
    session: Session = Depends(get_session),
):
    """Create a new assignment (owner_id optional in demo mode)."""

    try:
        data = payload.model_dump(exclude_none=True)
        assignment = Assignment(**data)

        session.add(assignment)
        session.commit()
        session.refresh(assignment)

        return assignment
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("Failed to create assignment titled '%s'", payload.title)
        raise HTTPException(
            status_code=500,
            detail="Unable to create assignment right now.",
        ) from exc


# ----------------------------------------------------------
# GET /assignments/{assignment_id}
# Public — students can load assignments
# ----------------------------------------------------------
@router.get("/{assignment_id}", response_model=AssignmentOut)
def get_assignment(assignment_id: str, session: Session = Depends(get_session)):
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment


# ----------------------------------------------------------
# GET /assignments/
# Instructor can view only their assignments
# ----------------------------------------------------------
@router.get("/", response_model=list[AssignmentOut])
def list_assignments(
    owner_id: str | None = Query(
        default=None,
        description="Optionally filter assignments by owner_id.",
    ),
    session: Session = Depends(get_session),
):
    stmt = select(Assignment)
    if owner_id:
        stmt = stmt.where(Assignment.owner_id == owner_id)
    return session.exec(stmt).all()


# ----------------------------------------------------------
# DELETE /assignments/{assignment_id}
# Instructor removes assignment + its responses
# ----------------------------------------------------------
@router.delete("/{assignment_id}")
def delete_assignment(assignment_id: str, session: Session = Depends(get_session)):
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    try:
        responses = session.exec(
            select(Response).where(Response.assignment_id == assignment_id)
        ).all()

        for response in responses:
            session.delete(response)

        session.delete(assignment)
        session.commit()
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("Failed to delete assignment '%s'", assignment_id)
        raise HTTPException(
            status_code=500,
            detail="Unable to delete assignment right now.",
        ) from exc

    return {"message": "Assignment and associated responses deleted successfully"}


# ----------------------------------------------------------
# OPTIONAL: Manual token generation for debugging
# ----------------------------------------------------------
@router.post("/token")
def generate_token():
    raise HTTPException(
        status_code=503,
        detail="JWT token generation is disabled while demo mode is active.",
    )
