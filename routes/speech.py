# routes/speech.py

from __future__ import annotations

import io
import os

from fastapi import APIRouter, File, HTTPException, UploadFile
from openai import OpenAI, OpenAIError

router = APIRouter(tags=["speech"])

_client: OpenAI | None = None
_WHISPER_ENV_KEYS = (
    "OPENAI_WHISPER_MODEL",
    "OPENAI_WHISPER",
    "WHISPER_MODEL",
)
_AUDIO_EXTENSIONS = (".webm", ".wav", ".mp3", ".m4a", ".m4v", ".mp4")


def _get_client() -> OpenAI:
    global _client

    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="OPENAI_API_KEY not configured on the server.",
            )
        _client = OpenAI(api_key=api_key)

    return _client


def _resolve_model_name() -> str:
    """
    Resolve the Whisper model name from the supported environment variables,
    defaulting to OpenAI's Whisper API (`whisper-1`) when none are set.
    """

    for env_key in _WHISPER_ENV_KEYS:
        raw_value = os.getenv(env_key)
        if raw_value:
            return raw_value.strip()

    # Fall back to the canonical Whisper model supported by OpenAI.
    return "whisper-1"


def _normalize_transcription_result(transcription: object) -> str:
    """
    `client.audio.transcriptions.create(response_format="text")` currently
    returns a plain string, but older SDK builds return an object with a `.text`
    attribute. Normalize both shapes to a trimmed string to keep the route
    resilient to SDK upgrades.
    """

    if transcription is None:
        return ""
    if isinstance(transcription, str):
        return transcription.strip()
    text_attr = getattr(transcription, "text", "")
    if isinstance(text_attr, str):
        return text_attr.strip()
    return ""


async def _transcribe_upload(file: UploadFile) -> dict[str, str]:
    filename = (file.filename or "").lower()
    if not filename.endswith(_AUDIO_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty audio file")

    audio_buffer = io.BytesIO(content)
    audio_buffer.name = file.filename or "audio.webm"

    model_name = _resolve_model_name()

    try:
        client = _get_client()
        transcription = client.audio.transcriptions.create(
            model=model_name,
            file=audio_buffer,
            response_format="text",
        )
    except OpenAIError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Transcription failed: {exc}",
        ) from exc

    text = _normalize_transcription_result(transcription)
    status = "success" if text else "empty"

    return {"transcription": text or "No speech detected in audio", "status": status}


@router.post("/speech/upload-audio/")
async def upload_audio(file: UploadFile = File(...)):
    """
    Legacy endpoint retained for backward compatibility with older clients.
    """

    return await _transcribe_upload(file)


@router.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Primary endpoint for Whisper transcription used by the Vercel deployment.
    """

    return await _transcribe_upload(file)
