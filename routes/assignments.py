# routes/assignments.py
# ==========================================================
# Routes for creating and retrieving assignments.
# Demo mode removes JWT requirements for easier testing.
# ==========================================================

import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
from middleware.auth import require_user_id, get_optional_user_id

# ----------------------------------------------------------
# Router setup
# ----------------------------------------------------------
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assignments", tags=["assignments"])
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in {"1", "true", "yes", "on"}
SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie"}


def _snapshot_headers(headers) -> dict[str, str]:
    """Return a sanitized copy of request headers for logging purposes."""
    snapshot: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADERS:
            snapshot[key] = "***redacted***"
        else:
            snapshot[key] = value
    return snapshot


def _resolve_owner_id(payload_owner_id: str | None, resolved_user_id: str) -> str:
    """Determine which owner id to persist on the assignment record."""
    
    # Always use the authenticated user ID from Clerk token
    if payload_owner_id and payload_owner_id != resolved_user_id:
        logger.warning(
            "Payload owner_id '%s' does not match authenticated user '%s'; "
            "using the authenticated id.",
            payload_owner_id,
            resolved_user_id,
        )
    return resolved_user_id


# ----------------------------------------------------------
# Draft Endpoints
# ----------------------------------------------------------
@router.post("/drafts", response_model=AssignmentDraftOut, status_code=201)
def create_assignment_draft(
    payload: AssignmentDraftCreate,
    session: Session = Depends(get_session),
    current_user_id: str = Depends(require_user_id),
):
    """Create a new assignment draft for the authenticated owner."""

    try:
        data = payload.model_dump(exclude_none=True)
        # Always use the authenticated user ID
        data["owner_id"] = current_user_id
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
        logger.exception("Failed to create assignment draft for owner '%s'", current_user_id)
        raise HTTPException(
            status_code=500,
            detail="Unable to save assignment draft right now.",
        ) from exc


@router.get("/drafts", response_model=list[AssignmentDraftOut])
def list_assignment_drafts(
    session: Session = Depends(get_session),
    current_user_id: str = Depends(require_user_id),
):
    """Return all drafts for the authenticated instructor ordered by last update."""

    stmt = (
        select(AssignmentDraft)
        .where(AssignmentDraft.owner_id == current_user_id)
        .order_by(AssignmentDraft.updated_at.desc())
    )
    return session.exec(stmt).all()


@router.patch("/drafts/{draft_id}", response_model=AssignmentDraftOut)
def update_assignment_draft(
    draft_id: str,
    payload: AssignmentDraftUpdate,
    session: Session = Depends(get_session),
    current_user_id: str = Depends(require_user_id),
):
    """Update mutable fields on a draft. Used by 30-second auto-save."""

    draft = session.get(AssignmentDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    
    # Ensure the draft belongs to the authenticated user
    if draft.owner_id != current_user_id:
        raise HTTPException(
            status_code=403,
            detail="Draft does not belong to the authenticated user.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    # Don't allow changing the owner_id
    update_data.pop("owner_id", None)
    
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
@router.post("/", response_model=AssignmentOut, status_code=201)
def create_assignment(
    payload: AssignmentCreate,
    request: Request,
    session: Session = Depends(get_session),
    current_user_id: str | None = Depends(get_optional_user_id),
):
    """Create a new assignment owned by the authenticated instructor."""

    if not current_user_id:
        headers_snapshot = _snapshot_headers(request.headers)
        body_snapshot = payload.model_dump()
        if DEMO_MODE and payload.owner_id:
            current_user_id = payload.owner_id
        else:
            failure_reason = (
                "demo mode request missing owner_id"
                if DEMO_MODE
                else "missing Authorization header outside demo mode"
            )
            logger.warning(
                "Assignment creation rejected: %s. headers=%s body=%s",
                failure_reason,
                headers_snapshot,
                body_snapshot,
            )
            if DEMO_MODE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Demo mode requires owner_id in the body when no Clerk token is provided.",
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Authorization header.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    try:
        draft_id = payload.draft_id
        owner_id = _resolve_owner_id(payload.owner_id, current_user_id)
        data = payload.model_dump(exclude_none=True, exclude={"draft_id", "owner_id"})
        data["owner_id"] = owner_id

        draft_to_delete = None
        if draft_id:
            draft_to_delete = session.get(AssignmentDraft, draft_id)
            if not draft_to_delete:
                raise HTTPException(status_code=404, detail="Draft not found")
            if draft_to_delete.owner_id != owner_id:
                raise HTTPException(
                    status_code=403,
                    detail="Draft does not belong to the authenticated instructor.",
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
    session: Session = Depends(get_session),
    current_user_id: str = Depends(require_user_id),
):
    """Return only assignments owned by the authenticated instructor."""

    stmt = select(Assignment).where(Assignment.owner_id == current_user_id)
    return session.exec(stmt).all()


# ----------------------------------------------------------
# DELETE /assignments/{assignment_id}
# Instructor removes assignment + its responses
# ----------------------------------------------------------
@router.delete("/{assignment_id}")
def delete_assignment(
    assignment_id: str,
    session: Session = Depends(get_session),
    current_user_id: str = Depends(require_user_id),
):
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    if assignment.owner_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assignment does not belong to the authenticated instructor.",
        )

    logger.info(
        "Deleting assignment '%s' (%s)",
        assignment_id,
        assignment.title,
    )

    deleted_responses = 0

    try:
        responses = session.exec(
            select(Response).where(Response.assignment_id == assignment_id)
        ).all()
        deleted_responses = len(responses)

        for response in responses:
            session.delete(response)

        session.flush()  # ensure responses are removed before deleting assignment
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
            detail="Unable to delete assignment right now.",
        ) from exc

    response_body: dict[str, object] = {
        "message": "Assignment deleted successfully.",
        "responses_deleted": deleted_responses,
    }

    return response_body


# ----------------------------------------------------------
# OPTIONAL: Manual token generation for debugging
# ----------------------------------------------------------
@router.post("/token")
def generate_token():
    raise HTTPException(
        status_code=503,
        detail="JWT token generation is disabled while demo mode is active.",
    )
