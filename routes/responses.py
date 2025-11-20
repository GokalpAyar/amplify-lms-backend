# routes/responses.py

from __future__ import annotations

import json
import logging
import os
import posixpath
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlmodel import Session, select
from starlette.datastructures import FormData

from audio_storage import (
    AudioStorageConfigError,
    AudioStorageDownloadError,
    AudioStorageError,
    AudioStorageUploadError,
    get_audio_storage,
)
from db import get_session
from models import Assignment, Response
from schemas import ResponseCreate, ResponseOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/responses", tags=["responses"])

_DEFAULT_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB
_AUDIO_FIELD_KEYS = (
    "audio",
    "audio_file",
    "audioFile",
    "recording",
    "voice",
    "voiceRecording",
    "recording_file",
    "audioBlob",
    "audio_blob",
)
_ALLOWED_AUDIO_EXTENSIONS = {
    ".webm",
    ".wav",
    ".mp3",
    ".m4a",
    ".m4v",
    ".mp4",
    ".ogg",
    ".oga",
    ".flac",
    ".aac",
}
_ALLOWED_VIDEO_MIME_TYPES = {"video/webm", "video/mp4"}


@router.post("/", response_model=ResponseOut)
async def create_response(
    request: Request,
    session: Session = Depends(get_session),
):
    """Create a new student response, optionally persisting an audio attachment."""

    payload, audio_upload = await _extract_payload(request)
    audio_metadata: dict[str, Any] = {}
    if audio_upload is not None:
        audio_metadata = await _persist_audio_upload(audio_upload)

    uploaded_audio_path = audio_metadata.get("audio_storage_path")

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

        response = Response(**payload.model_dump(), **audio_metadata)

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
        _safe_delete_audio(uploaded_audio_path)
        raise
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        _safe_delete_audio(uploaded_audio_path)
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


@router.get("/{response_id}/audio")
def stream_response_audio(
    response_id: str,
    session: Session = Depends(get_session),
):
    """Stream the stored audio file for a specific response."""

    response_record = session.get(Response, response_id)
    if not response_record:
        raise HTTPException(status_code=404, detail="Response not found")
    if not response_record.audio_storage_path:
        raise HTTPException(status_code=404, detail="No audio recording on file for this response.")

    try:
        storage = get_audio_storage()
    except AudioStorageConfigError as exc:
        raise HTTPException(
            status_code=503,
            detail="Audio storage is not configured on the server.",
        ) from exc

    try:
        audio_bytes = storage.download_audio(response_record.audio_storage_path)
    except AudioStorageDownloadError as exc:
        logger.exception("Failed to download audio for response %s", response_id)
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve the audio recording right now.",
        ) from exc
    except AudioStorageError as exc:
        logger.exception("Unexpected storage failure while downloading audio for %s", response_id)
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve the audio recording right now.",
        ) from exc

    media_type = response_record.audio_mime_type or "application/octet-stream"
    filename = _build_audio_filename(response_record)
    headers = {
        "Content-Length": str(len(audio_bytes)),
        "Content-Disposition": f'attachment; filename="{filename}"',
    }

    return StreamingResponse(iter([audio_bytes]), media_type=media_type, headers=headers)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _extract_payload(request: Request) -> tuple[ResponseCreate, UploadFile | None]:
    content_type = (request.headers.get("content-type") or "").lower()
    audio_upload: UploadFile | None = None
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


def _extract_audio_upload(form: FormData) -> UploadFile | None:
    for key in _AUDIO_FIELD_KEYS:
        value = form.get(key)
        if isinstance(value, UploadFile):
            return value

    for _, value in form.items():
        if isinstance(value, UploadFile):
            return value

    return None


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


async def _persist_audio_upload(upload: UploadFile) -> dict[str, Any]:
    """
    Validate and persist an uploaded audio file to Supabase Storage.
    Returns the metadata that should be saved with the Response.
    """

    try:
        data = await upload.read()
    finally:
        await upload.close()

    if not data:
        raise HTTPException(status_code=400, detail="Audio file cannot be empty.")

    file_size = len(data)
    max_bytes = _get_audio_max_bytes()
    if file_size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file exceeds {_format_file_size(max_bytes)} limit.",
        )

    filename = upload.filename or ""
    extension = _detect_extension(filename)
    mime_type_raw = (upload.content_type or "").strip().lower()
    mime_type = mime_type_raw or "application/octet-stream"

    if not _is_supported_audio_type(mime_type, extension):
        raise HTTPException(status_code=400, detail="Unsupported audio file type.")

    try:
        storage = get_audio_storage()
    except AudioStorageConfigError as exc:
        logger.error("Audio upload received but Supabase Storage is not configured.")
        raise HTTPException(
            status_code=503,
            detail="Audio storage is not configured on the server.",
        ) from exc

    try:
        stored = storage.upload_audio(
            data=data,
            content_type=mime_type,
            extension=extension,
        )
    except AudioStorageUploadError as exc:
        logger.exception("Supabase Storage rejected the audio upload.")
        raise HTTPException(
            status_code=502,
            detail="Unable to store audio recording right now.",
        ) from exc
    except AudioStorageError as exc:
        logger.exception("Unexpected Supabase Storage failure during audio upload.")
        raise HTTPException(
            status_code=502,
            detail="Unable to store audio recording right now.",
        ) from exc

    logger.info(
        "Stored response audio (%s, %s) at %s",
        _format_file_size(file_size),
        mime_type,
        stored.storage_path,
    )

    return {
        "audio_storage_path": stored.storage_path,
        "audio_file_url": stored.public_url,
        "audio_file_size": file_size,
        "audio_mime_type": mime_type,
    }


def _is_supported_audio_type(mime_type: str | None, extension: str | None) -> bool:
    normalized_mime = (mime_type or "").lower()
    if normalized_mime.startswith("audio/"):
        return True
    if normalized_mime in _ALLOWED_VIDEO_MIME_TYPES:
        return True
    if extension:
        return extension.lower() in _ALLOWED_AUDIO_EXTENSIONS
    return False


def _detect_extension(filename: str | None) -> str | None:
    if not filename:
        return None
    _, ext = os.path.splitext(filename)
    if not ext:
        return None
    return ext.lower()


def _get_audio_max_bytes() -> int:
    raw_bytes = os.getenv("RESPONSE_AUDIO_MAX_BYTES")
    if raw_bytes:
        try:
            limit = int(raw_bytes)
            if limit > 0:
                return limit
            logger.warning("RESPONSE_AUDIO_MAX_BYTES must be positive; falling back to default.")
        except ValueError:
            logger.warning("Invalid RESPONSE_AUDIO_MAX_BYTES value: %s", raw_bytes)

    raw_mb = os.getenv("RESPONSE_AUDIO_MAX_MB")
    if raw_mb:
        try:
            mb_value = float(raw_mb)
            limit = int(mb_value * 1024 * 1024)
            if limit > 0:
                return limit
            logger.warning("RESPONSE_AUDIO_MAX_MB must be positive; falling back to default.")
        except ValueError:
            logger.warning("Invalid RESPONSE_AUDIO_MAX_MB value: %s", raw_mb)

    return _DEFAULT_MAX_AUDIO_BYTES


def _format_file_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("bytes", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "bytes":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _safe_delete_audio(storage_path: str | None) -> None:
    if not storage_path:
        return

    try:
        storage = get_audio_storage()
    except AudioStorageConfigError:
        logger.warning("Audio cleanup skipped because storage is not configured.")
        return

    try:
        storage.delete_audio(storage_path)
        logger.info("Deleted orphaned audio object %s after failed response creation.", storage_path)
    except AudioStorageError:
        logger.warning("Failed to delete audio object %s during rollback.", storage_path, exc_info=True)


def _build_audio_filename(response_record: Response) -> str:
    if response_record.audio_storage_path:
        basename = posixpath.basename(response_record.audio_storage_path)
        if basename:
            return basename

    stem = (response_record.studentName or "response-audio").strip().replace(" ", "_")
    stem = stem or "response-audio"
    return f"{stem}.webm"

