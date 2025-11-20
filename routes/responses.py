# routes/responses.py

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlmodel import Session, select
from starlette.datastructures import FormData

from db import get_session
from models import Assignment, Response
from schemas import ResponseCreate, ResponseOut

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


@router.get("/", response_model=list[ResponseOut])
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

    responses = session.exec(stmt).all()
    return responses


@router.get("/{assignment_id}", response_model=list[ResponseOut])
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

