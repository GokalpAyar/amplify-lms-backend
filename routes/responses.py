# routes/responses.py

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Header
from pydantic import ValidationError
from sqlmodel import Session, select
from starlette.datastructures import FormData

from db import get_session
from models import Assignment, Response, AccuracyRating
from schemas import (
    AccuracyRatingOut,
    AccuracyRatingPayload,
    ResponseCreate,
    ResponseOut,
    StudentAccuracyRatingPayload,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/responses", tags=["responses"])


@router.post("/", response_model=ResponseOut)
async def create_response(
    request: Request,
    session: Session = Depends(get_session),
):
    """Create a new student response without persisting audio attachments."""

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

        return response
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("Failed to store submission for assignment %s: %s", payload.assignment_id, exc)
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


@router.post("/{response_id}/accuracy-rating", response_model=AccuracyRatingOut)
def upsert_accuracy_rating(
    response_id: str,
    payload: AccuracyRatingPayload,
    session: Session = Depends(get_session),
):
    """Create or update the transcription accuracy rating for a response."""

    response = session.get(Response, response_id)
    if not response:
        raise HTTPException(status_code=404, detail="Response not found")

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
    student_j_number_header: str | None = Header(
        default=None,
        alias="X-Student-JNumber",
        description="Student identifier header used to validate ownership.",
    ),
    student_j_number_query: str | None = Query(
        default=None,
        alias="student_j_number",
        description="Fallback student identifier passed as a query parameter.",
    ),
):
    """Allow students to rate the accuracy of their own transcript."""

    response = session.get(Response, response_id)
    if not response:
        raise HTTPException(status_code=404, detail="Response not found")

    student_identifier = _resolve_student_identifier(student_j_number_header, student_j_number_query)
    if response.jNumber != student_identifier:
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to rate this response.",
        )

    response.student_accuracy_rating = payload.rating
    response.student_rating_comment = _clean_comment(payload.comment)

    try:
        session.add(response)
        session.commit()
        session.refresh(response)
        return response
    except HTTPException:
        session.rollback()
        raise
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


def _resolve_student_identifier(header_value: str | None, query_value: str | None) -> str:
    identifier = (header_value or query_value or "").strip()
    if not identifier:
        raise HTTPException(
            status_code=400,
            detail="Student identifier is required to submit a rating.",
        )
    return identifier


def _clean_comment(comment: str | None) -> str | None:
    if comment is None:
        return None
    stripped = comment.strip()
    return stripped or None

