# routes/responses.py

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from jose import JWTError
from pydantic import ValidationError
from sqlmodel import Session, select
from starlette.datastructures import FormData

from db import get_session
from models import AccuracyRating, Assignment, Response
from schemas import (
    AccuracyRatingOut,
    AccuracyRatingPayload,
    ResponseCreate,
    ResponseOut,
    StudentAccuracyRatingPayload,
)
from supabase_auth import get_current_instructor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/responses", tags=["responses"])


# --------------------------------------------------------------------------- #
# Public (students, no login)
# --------------------------------------------------------------------------- #
@router.post("/", response_model=ResponseOut)
async def create_response(
    request: Request,
    session: Session = Depends(get_session),
):
    """Create a new student response without persisting audio attachments.
    Public endpoint: students do NOT log in.
    """

    payload = await _extract_payload(request)

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

        return _serialize_response(response)
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception(
            "Failed to store submission for assignment %s: %s",
            payload.assignment_id,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to store response right now.",
        ) from exc


# --------------------------------------------------------------------------- #
# Instructor-only (Supabase login required)
# --------------------------------------------------------------------------- #
@router.get("/", response_model=list[ResponseOut])
def list_responses(
    session: Session = Depends(get_session),
    user=Depends(get_current_instructor),
):
    """List responses for the logged-in instructor only."""

    try:
        assignment_ids = session.exec(
            select(Assignment.id).where(Assignment.owner_id == user["user_id"])
        ).all()

        if not assignment_ids:
            return []

        responses = session.exec(
            select(Response).where(Response.assignment_id.in_(assignment_ids))
        ).all()

        return _serialize_response_list(responses)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list responses for user %s: %s", user["user_id"], exc)
        raise HTTPException(status_code=500, detail="Unable to list responses right now.") from exc


@router.get("/{assignment_id}", response_model=list[ResponseOut])
def get_responses_for_assignment(
    assignment_id: str,
    session: Session = Depends(get_session),
    user=Depends(get_current_instructor),
):
    """Get responses for a specific assignment (instructor-only)."""

    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    # Only the owner can view submissions
    if str(assignment.owner_id) != user["user_id"]:
        raise HTTPException(
            status_code=403,
            detail="Not allowed to view submissions for this assignment",
        )

    responses = session.exec(
        select(Response).where(Response.assignment_id == assignment_id)
    ).all()

    return _serialize_response_list(responses)


@router.post("/{response_id}/accuracy-rating", response_model=AccuracyRatingOut)
def upsert_accuracy_rating(
    response_id: str,
    payload: AccuracyRatingPayload,
    session: Session = Depends(get_session),
    user=Depends(get_current_instructor),
):
    """Create or update the transcription accuracy rating for a response (instructor-only)."""

    response = session.get(Response, response_id)
    if not response:
        raise HTTPException(status_code=404, detail="Response not found")

    # Ensure the response belongs to an assignment owned by the instructor
    assignment = session.get(Assignment, response.assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if str(assignment.owner_id) != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not allowed")

    rating_record = session.exec(
        select(AccuracyRating).where(AccuracyRating.response_id == response_id)
    ).first()

    try:
        if rating_record:
            rating_record.rating = payload.rating
            rating_record.bias_notes = payload.bias_notes
            rating_record.needs_review = payload.needs_review
            rating_record.updated_at = datetime.utcnow()
        else:
            rating_record = AccuracyRating(
                response_id=response_id,
                rating=payload.rating,
                bias_notes=payload.bias_notes,
                needs_review=payload.needs_review,
            )
            session.add(rating_record)

        session.commit()
        session.refresh(rating_record)
        return rating_record
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("Failed to save accuracy rating for %s: %s", response_id, exc)
        raise HTTPException(
            status_code=500,
            detail="Unable to save accuracy rating right now.",
        ) from exc


@router.put("/{response_id}/accuracy-rating", response_model=ResponseOut)
def update_student_accuracy_rating(
    response_id: str,
    payload: StudentAccuracyRatingPayload,
    session: Session = Depends(get_session),
):
    """Allow students to rate the accuracy of their own transcript.
    Public endpoint (no login). If you want to lock this down later, we can.
    """

    response = session.get(Response, response_id)
    if not response:
        raise HTTPException(status_code=404, detail="Response not found")

    # SIMPLIFIED: Just update the rating without complex student validation
    response.student_accuracy_rating = payload.rating
    response.student_rating_comment = payload.comment

    try:
        session.add(response)
        session.commit()
        session.refresh(response)
        return _serialize_response(response)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("Failed to update student accuracy rating for %s: %s", response_id, exc)
        raise HTTPException(
            status_code=500,
            detail="Unable to update accuracy rating right now.",
        ) from exc


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _extract_payload(request: Request) -> ResponseCreate:
    content_type = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in content_type:
        form = await request.form()
        payload_dict = _payload_from_form(form)
    else:
        try:
            payload_dict = await request.json()
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON payload.") from exc
        if not isinstance(payload_dict, dict):
            raise HTTPException(
                status_code=400,
                detail="JSON payload must be an object.",
            )

    try:
        payload = ResponseCreate(**payload_dict)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    return payload


def _payload_from_form(form: FormData) -> dict[str, Any]:
    answers_raw = _first_match(form, "answers")
    transcripts_raw = _first_match(form, "transcripts")

    data: dict[str, Any] = {
        "assignment_id": _first_match(form, "assignment_id", "assignmentId"),
        "studentName": _first_match(form, "studentName"),
        "jNumber": _first_match(form, "jNumber", "j_number"),
        "answers": _parse_json_field(answers_raw, "answers"),
        "transcripts": _parse_json_field(transcripts_raw, "transcripts"),
        "audio_file_url": _first_match(
            form,
            "audio_file_url",
            "audioFileUrl",
            "audio_url",
        ),
    }
    return data


def _first_match(form: FormData, *keys: str) -> Any:
    for key in keys:
        if key in form and form.get(key) not in (None, ""):
            return form.get(key)
    return None


def _parse_json_field(raw_value: Any, field_name: str) -> Any:
    if isinstance(raw_value, (dict, list)):
        return raw_value
    if isinstance(raw_value, str):
        value = raw_value.strip()
        if not value:
            raise HTTPException(
                status_code=400,
                detail=f"Field '{field_name}' cannot be empty.",
            )
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Field '{field_name}' must contain valid JSON.",
            ) from exc
    if raw_value is None:
        raise HTTPException(
            status_code=400,
            detail=f"Field '{field_name}' is required in the form payload.",
        )
    return raw_value


def _serialize_response(response: Response) -> dict[str, Any]:
    """Serialize a Response model to ensure rating fields are always present."""
    return ResponseOut.model_validate(response, from_attributes=True).model_dump()


def _serialize_response_list(responses: Sequence[Response]) -> list[dict[str, Any]]:
    return [_serialize_response(response) for response in responses]
