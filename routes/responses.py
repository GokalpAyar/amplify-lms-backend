# routes/responses.py

from __future__ import annotations

import io
import json
import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlmodel import Session, select
from starlette.datastructures import FormData

from audio_storage import AudioStorageError, try_get_audio_storage
from db import get_session
from models import Assignment, Response
from schemas import ResponseCreate, ResponseOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/responses", tags=["responses"])


_ALLOWED_MIME_TYPES = {
    "audio/webm",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/aac",
    "audio/ogg",
    "audio/oga",
    "audio/3gpp",
    "audio/3gpp2",
}
_ALLOWED_EXTENSIONS = {
    ".webm",
    ".wav",
    ".mp3",
    ".m4a",
    ".mp4",
    ".aac",
    ".ogg",
    ".oga",
}


def _resolve_max_audio_bytes() -> int:
    """
    Resolve the maximum audio file size from environment variables.
    Defaults to 10MB (10 * 1024 * 1024 bytes) for audio uploads.
    """
    max_size_mb = int(os.getenv("MAX_AUDIO_SIZE_MB", "10"))
    return max_size_mb * 1024 * 1024  # Convert MB to bytes


_MAX_AUDIO_BYTES = _resolve_max_audio_bytes()
_MAX_AUDIO_MB = round(_MAX_AUDIO_BYTES / (1024 * 1024), 2)


@router.post("/", response_model=ResponseOut)
async def create_response(
    request: Request,
    session: Session = Depends(get_session),
):
    """Create a new student response, optionally including an audio recording."""

    payload, audio_upload = await _extract_payload(request)
    storage = None
    storage_path: str | None = None

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

        audio_bytes = None
        audio_meta = None

        if audio_upload:
            audio_bytes, audio_meta = await _read_and_validate_audio(audio_upload)
            storage = try_get_audio_storage()
            if not storage:
                raise HTTPException(
                    status_code=503,
                    detail="Audio storage is not configured on the server.",
                )
            try:
                stored = storage.upload_audio(
                    data=audio_bytes,
                    content_type=audio_meta["content_type"],
                    extension=audio_meta["extension"],
                )
            except AudioStorageError as exc:
                logger.exception("Supabase upload failed for response %s", payload.jNumber)
                raise HTTPException(
                    status_code=502,
                    detail="Unable to store audio recording.",
                ) from exc
            audio_meta["storage_path"] = stored.storage_path
            audio_meta["public_url"] = stored.public_url
            storage_path = stored.storage_path

        response = Response(**payload.model_dump())
        if audio_meta:
            response.audio_file_url = audio_meta.get("public_url")
            response.audio_storage_path = audio_meta.get("storage_path")
            response.audio_mime_type = audio_meta.get("content_type")
            response.audio_file_size = audio_meta.get("size")

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
        if storage and storage_path:
            _cleanup_uploaded_audio(storage, storage_path)
        raise
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        if storage and storage_path:
            _cleanup_uploaded_audio(storage, storage_path)
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


@router.get("/{response_id}/audio")
def get_response_audio(response_id: str, session: Session = Depends(get_session)):
    """Stream the stored audio recording for a given response."""

    response = session.get(Response, response_id)
    if not response:
        raise HTTPException(status_code=404, detail="Response not found")
    if not response.audio_storage_path:
        raise HTTPException(
            status_code=404,
            detail="This response does not have an audio recording.",
        )

    storage = try_get_audio_storage()
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Audio storage is not configured on the server.",
        )

    try:
        audio_bytes = storage.download_audio(response.audio_storage_path)
    except AudioStorageError as exc:
        logger.exception("Failed to download audio for response %s", response_id)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch audio recording.",
        ) from exc

    media_type = response.audio_mime_type or "application/octet-stream"
    filename = _build_download_filename(response, response.audio_storage_path)

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Length": str(len(audio_bytes)),
    }

    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type=media_type,
        headers=headers,
    )


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


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _extract_payload(request: Request) -> tuple[ResponseCreate, UploadFile | None]:
    content_type = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in content_type:
        form = await request.form()
        payload_dict = _payload_from_form(form)
        audio_upload = _extract_audio_upload(form)
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
        audio_upload = None

    try:
        payload = ResponseCreate(**payload_dict)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    return payload, audio_upload


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


def _extract_audio_upload(form: FormData) -> UploadFile | None:
    for key in ("audio_file", "audio", "voice", "file"):
        value = form.get(key)
        if isinstance(value, UploadFile):
            return value
    return None


async def _read_and_validate_audio(
    audio_file: UploadFile,
) -> tuple[bytes, dict[str, Any]]:
    filename = (audio_file.filename or "").strip()
    extension = Path(filename).suffix.lower() if filename else ""
    mime = _normalize_mime(audio_file.content_type)

    if not mime and filename:
        guessed, _ = mimetypes.guess_type(filename)
        mime = _normalize_mime(guessed)

    if not _is_supported_audio(mime, extension):
        logger.warning("Unsupported audio upload: filename=%s mime=%s", filename, mime)
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio format. Allowed extensions: "
            + ", ".join(sorted(_ALLOWED_EXTENSIONS)),
        )

    content = await audio_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Audio file is empty.")

    if len(content) > _MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file is too large (max {_MAX_AUDIO_MB} MB).",
        )

    return content, {
        "size": len(content),
        "content_type": mime or "application/octet-stream",
        "extension": extension or None,
    }


def _normalize_mime(mime: str | None) -> str:
    if not mime:
        return ""
    return mime.split(";")[0].strip().lower()


def _is_supported_audio(mime: str, extension: str) -> bool:
    return (mime in _ALLOWED_MIME_TYPES) or (extension in _ALLOWED_EXTENSIONS)


def _cleanup_uploaded_audio(storage, storage_path: str) -> None:
    try:
        storage.delete_audio(storage_path)
    except AudioStorageError as exc:  # noqa: BLE001
        logger.warning("Failed to cleanup orphaned audio '%s': %s", storage_path, exc)


def _build_download_filename(response: Response, storage_path: str) -> str:
    base_name = response.studentName or "response-audio"
    safe_base = re.sub(r"[^A-Za-z0-9_-]+", "-", base_name).strip("-") or "response-audio"

    extension = Path(storage_path).suffix or ""
    if not extension and response.audio_mime_type:
        guessed = mimetypes.guess_extension(response.audio_mime_type)
        if guessed:
            extension = guessed
    extension = extension or ".webm"

    return f"{safe_base}-{response.id}{extension}"