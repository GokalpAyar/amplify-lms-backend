# routes/assignments.py
# ==========================================================
# Routes for creating and retrieving assignments.
# Demo mode removes JWT requirements for easier testing.
# ==========================================================

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from db import get_session
from models import Assignment, AssignmentDraft, Response
from schemas import (
    AssignmentCreate,
    AssignmentDraftCreate,
    AssignmentDraftOut,
    AssignmentDraftUpdate,
    AssignmentOut,
)

# ----------------------------------------------------------
# Router setup
# ----------------------------------------------------------
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assignments", tags=["assignments"])


# ----------------------------------------------------------
# Draft Endpoints
# ----------------------------------------------------------
@router.post("/drafts", response_model=AssignmentDraftOut, status_code=201)
def create_assignment_draft(
    payload: AssignmentDraftCreate,
    session: Session = Depends(get_session),
):
    """Create a new assignment draft for the given owner."""

    try:
        data = payload.model_dump(exclude_none=True)
        draft = AssignmentDraft(**data)
        session.add(draft)
        session.commit()
        session.refresh(draft)
        return draft
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("Failed to create assignment draft for owner '%s'", payload.owner_id)
        raise HTTPException(
            status_code=500,
            detail="Unable to save assignment draft right now.",
        ) from exc


@router.get("/drafts/{user_id}", response_model=list[AssignmentDraftOut])
def list_assignment_drafts(user_id: str, session: Session = Depends(get_session)):
    """Return all drafts for a specific instructor ordered by last update."""

    stmt = (
        select(AssignmentDraft)
        .where(AssignmentDraft.owner_id == user_id)
        .order_by(AssignmentDraft.updated_at.desc())
    )
    return session.exec(stmt).all()


@router.patch("/drafts/{draft_id}", response_model=AssignmentDraftOut)
def update_assignment_draft(
    draft_id: str,
    payload: AssignmentDraftUpdate,
    session: Session = Depends(get_session),
):
    """Update mutable fields on a draft. Used by 30-second auto-save."""

    draft = session.get(AssignmentDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    update_data = payload.model_dump(exclude_unset=True)
    if update_data:
        for key, value in update_data.items():
            setattr(draft, key, value)
    draft.updated_at = datetime.utcnow()

    try:
        session.add(draft)
        session.commit()
        session.refresh(draft)
        return draft
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("Failed to update assignment draft '%s'", draft_id)
        raise HTTPException(
            status_code=500,
            detail="Unable to update assignment draft right now.",
        ) from exc

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
        draft_id = payload.draft_id
        data = payload.model_dump(exclude_none=True, exclude={"draft_id"})

        draft_to_delete = None
        if draft_id:
            draft_to_delete = session.get(AssignmentDraft, draft_id)
            if not draft_to_delete:
                raise HTTPException(status_code=404, detail="Draft not found")
            if payload.owner_id and draft_to_delete.owner_id != payload.owner_id:
                raise HTTPException(
                    status_code=403,
                    detail="Draft does not belong to the provided owner.",
                )

        assignment = Assignment(**data)

        session.add(assignment)
        if draft_to_delete:
            session.delete(draft_to_delete)
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
