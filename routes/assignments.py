# routes/assignments.py
# ==========================================================
# Routes for creating and retrieving assignments.
# Instructors authenticate via Supabase JWT.
# Students do NOT log in (they can load assignments by id).
# ==========================================================

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
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
from supabase_auth import get_current_instructor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assignments", tags=["assignments"])


# ----------------------------------------------------------
# Draft Endpoints (Frontend-compatible single-current-draft)
# ----------------------------------------------------------
@router.get("/draft", response_model=AssignmentDraftOut)
def get_current_assignment_draft(
    session: Session = Depends(get_session),
    user=Depends(get_current_instructor),
):
    """Return the most recently updated draft for the logged-in instructor."""
    draft = session.exec(
        select(AssignmentDraft)
        .where(AssignmentDraft.owner_id == user["user_id"])
        .order_by(AssignmentDraft.updated_at.desc())
    ).first()

    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    return draft


@router.put("/draft", response_model=AssignmentDraftOut)
def upsert_current_assignment_draft(
    payload: AssignmentDraftUpdate,
    session: Session = Depends(get_session),
    user=Depends(get_current_instructor),
):
    """
    Create or update the current instructor's draft.
    This matches the frontend autosave behavior.
    """
    draft = session.exec(
        select(AssignmentDraft)
        .where(AssignmentDraft.owner_id == user["user_id"])
        .order_by(AssignmentDraft.updated_at.desc())
    ).first()

    try:
        if not draft:
            draft = AssignmentDraft(
                owner_id=user["user_id"],
                title=payload.title,
                description=payload.description,
                questions=payload.questions,
            )
        else:
            update_data = payload.model_dump(exclude_unset=True, exclude={"owner_id"})
            for key, value in update_data.items():
                setattr(draft, key, value)
            draft.updated_at = datetime.utcnow()

        session.add(draft)
        session.commit()
        session.refresh(draft)
        return draft

    except HTTPException:
        session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        logger.exception("Integrity error while upserting current draft for user '%s'", user["user_id"])
        raise HTTPException(
            status_code=500,
            detail=f"Integrity error while saving draft: {str(exc)}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("Failed to upsert current draft for user '%s'", user["user_id"])
        raise HTTPException(
            status_code=500,
            detail=f"Unable to save assignment draft right now: {str(exc)}",
        ) from exc


@router.delete("/draft")
def delete_current_assignment_draft(
    session: Session = Depends(get_session),
    user=Depends(get_current_instructor),
):
    """Delete the most recently updated draft for the logged-in instructor."""
    draft = session.exec(
        select(AssignmentDraft)
        .where(AssignmentDraft.owner_id == user["user_id"])
        .order_by(AssignmentDraft.updated_at.desc())
    ).first()

    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    try:
        session.delete(draft)
        session.commit()
        return {"message": "Draft deleted successfully."}
    except IntegrityError as exc:
        session.rollback()
        logger.exception("Integrity error while deleting current draft for user '%s'", user["user_id"])
        raise HTTPException(
            status_code=500,
            detail=f"Integrity error while deleting draft: {str(exc)}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("Failed to delete current draft for user '%s'", user["user_id"])
        raise HTTPException(
            status_code=500,
            detail=f"Unable to delete draft right now: {str(exc)}",
        ) from exc


# ----------------------------------------------------------
# Optional multi-draft Endpoints (keep for future flexibility)
# ----------------------------------------------------------
@router.post("/drafts", response_model=AssignmentDraftOut, status_code=201)
def create_assignment_draft(
    payload: AssignmentDraftCreate,
    session: Session = Depends(get_session),
    user=Depends(get_current_instructor),
):
    """Create a new assignment draft for the logged-in instructor."""
    try:
        data = payload.model_dump(exclude_none=True, exclude={"owner_id"})
        data["owner_id"] = user["user_id"]

        draft = AssignmentDraft(**data)
        session.add(draft)
        session.commit()
        session.refresh(draft)
        return draft
    except HTTPException:
        session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        logger.exception("Integrity error while creating draft for user '%s'", user["user_id"])
        raise HTTPException(
            status_code=500,
            detail=f"Integrity error while creating draft: {str(exc)}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("Failed to create assignment draft for user '%s'", user["user_id"])
        raise HTTPException(
            status_code=500,
            detail=f"Unable to save assignment draft right now: {str(exc)}",
        ) from exc


@router.get("/drafts/me", response_model=list[AssignmentDraftOut])
def list_my_assignment_drafts(
    session: Session = Depends(get_session),
    user=Depends(get_current_instructor),
):
    """List drafts for the logged-in instructor."""
    drafts = session.exec(
        select(AssignmentDraft).where(AssignmentDraft.owner_id == user["user_id"])
    ).all()
    return drafts


@router.patch("/drafts/{draft_id}", response_model=AssignmentDraftOut)
def update_assignment_draft(
    draft_id: str,
    payload: AssignmentDraftUpdate,
    session: Session = Depends(get_session),
    user=Depends(get_current_instructor),
):
    """Update mutable fields on a specific draft."""
    draft = session.get(AssignmentDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    if str(draft.owner_id) != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not allowed to update this draft")

    update_data = payload.model_dump(exclude_unset=True, exclude={"owner_id"})
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
    except IntegrityError as exc:
        session.rollback()
        logger.exception("Integrity error while updating assignment draft '%s'", draft_id)
        raise HTTPException(
            status_code=500,
            detail=f"Integrity error while updating draft: {str(exc)}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("Failed to update assignment draft '%s'", draft_id)
        raise HTTPException(
            status_code=500,
            detail=f"Unable to update assignment draft right now: {str(exc)}",
        ) from exc


@router.delete("/drafts/{draft_id}")
def delete_assignment_draft(
    draft_id: str,
    session: Session = Depends(get_session),
    user=Depends(get_current_instructor),
):
    """Delete a specific draft (instructor-only)."""
    draft = session.get(AssignmentDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    if str(draft.owner_id) != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not allowed to delete this draft")

    try:
        session.delete(draft)
        session.commit()
        return {"message": "Draft deleted successfully."}
    except IntegrityError as exc:
        session.rollback()
        logger.exception("Integrity error while deleting draft '%s'", draft_id)
        raise HTTPException(
            status_code=500,
            detail=f"Integrity error while deleting draft: {str(exc)}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("Failed to delete draft '%s': %s", draft_id, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Unable to delete draft right now: {str(exc)}",
        ) from exc


# ----------------------------------------------------------
# Assignments (Instructor-only create/list/delete)
# ----------------------------------------------------------
@router.post("/", response_model=AssignmentOut)
def create_assignment(
    payload: AssignmentCreate,
    session: Session = Depends(get_session),
    user=Depends(get_current_instructor),
):
    """Create a new assignment (owner_id derived from Supabase token)."""
    try:
        draft_id = payload.draft_id

        data = payload.model_dump(exclude_none=True, exclude={"draft_id", "owner_id"})
        data["owner_id"] = user["user_id"]

        logger.info("Creating assignment for user_id=%s", user["user_id"])
        logger.info("Assignment payload keys=%s", list(data.keys()))
        logger.info("Questions type=%s", type(data.get("questions")).__name__)

        draft_to_delete = None
        if draft_id:
            draft_to_delete = session.get(AssignmentDraft, draft_id)
            if not draft_to_delete:
                raise HTTPException(status_code=404, detail="Draft not found")

            if str(draft_to_delete.owner_id) != user["user_id"]:
                raise HTTPException(status_code=403, detail="Draft does not belong to you.")

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
    except IntegrityError as exc:
        session.rollback()
        logger.exception("Integrity error while creating assignment")
        raise HTTPException(
            status_code=500,
            detail=f"Integrity error while creating assignment: {str(exc)}",
        ) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception("SQLAlchemy error while creating assignment")
        raise HTTPException(
            status_code=500,
            detail=f"Database error while creating assignment: {str(exc)}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("Failed to create assignment titled '%s'", payload.title)
        raise HTTPException(
            status_code=500,
            detail=f"Unable to create assignment right now: {str(exc)}",
        ) from exc


@router.get("/", response_model=list[AssignmentOut])
def list_assignments(
    session: Session = Depends(get_session),
    user=Depends(get_current_instructor),
):
    """List assignments belonging to the logged-in instructor."""
    stmt = select(Assignment).where(Assignment.owner_id == user["user_id"])
    return session.exec(stmt).all()


@router.delete("/{assignment_id}")
def delete_assignment(
    assignment_id: str,
    session: Session = Depends(get_session),
    user=Depends(get_current_instructor),
):
    """Delete an assignment and its responses (instructor-only)."""
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    if str(assignment.owner_id) != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not allowed to delete this assignment")

    logger.info(
        "Deleting assignment '%s' (%s) by user %s",
        assignment_id,
        assignment.title,
        user["user_id"],
    )

    deleted_responses = 0

    try:
        responses = session.exec(
            select(Response).where(Response.assignment_id == assignment_id)
        ).all()
        deleted_responses = len(responses)

        for response in responses:
            session.delete(response)

        session.flush()
        session.delete(assignment)
        session.commit()

        logger.info(
            "Deleted assignment '%s' and %s responses",
            assignment_id,
            deleted_responses,
        )

    except HTTPException:
        session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        logger.exception(
            "Foreign-key constraint prevented assignment '%s' deletion: %s",
            assignment_id,
            exc,
        )
        raise HTTPException(
            status_code=409,
            detail="Assignment still has linked responses. Please retry after confirming all submissions were removed.",
        ) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception(
            "Database error while deleting assignment '%s': %s",
            assignment_id,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Database error while deleting assignment. See server logs for details.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception(
            "Unexpected error while deleting assignment '%s': %s",
            assignment_id,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Unable to delete assignment right now: {str(exc)}",
        ) from exc

    return {
        "message": "Assignment deleted successfully.",
        "responses_deleted": deleted_responses,
    }


# ----------------------------------------------------------
# Public — students can load assignments by id
# ----------------------------------------------------------
@router.get("/{assignment_id}", response_model=AssignmentOut)
def get_assignment(assignment_id: str, session: Session = Depends(get_session)):
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment