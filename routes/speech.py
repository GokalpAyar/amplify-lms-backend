# routes/speech.py

from __future__ import annotations

import io
import os
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from openai import OpenAI, OpenAIError

router = APIRouter(tags=["speech"])
logger = logging.getLogger(__name__)

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
        logger.info(f"OpenAI API Key present: {bool(api_key)}")
        logger.info(f"OpenAI API Key starts with sk-: {api_key.startswith('sk-') if api_key else False}")
        logger.info(f"OpenAI API Key length: {len(api_key) if api_key else 0}")
        
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="OPENAI_API_KEY not configured on the server.",
            )
        _client = OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized successfully")

    return _client


def _resolve_model_name() -> str:
    """
    Resolve the Whisper model name from the supported environment variables,
    defaulting to OpenAI's Whisper API (`whisper-1`) when none are set.
    """
    for env_key in _WHISPER_ENV_KEYS:
        raw_value = os.getenv(env_key)
        if raw_value:
            model_name = raw_value.strip()
            logger.info(f"Using model from {env_key}: {model_name}")
            return model_name

    # Fall back to the canonical Whisper model supported by OpenAI.
    logger.info("Using default model: whisper-1")
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
    logger.info(f"Starting transcription for file: {file.filename}")
    
    filename = (file.filename or "").lower()
    logger.info(f"File extension check: {filename}")
    
    if not filename.endswith(_AUDIO_EXTENSIONS):
        logger.error(f"Unsupported audio format: {filename}")
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    content = await file.read()
    logger.info(f"File size: {len(content)} bytes")
    
    if not content:
        logger.error("Empty audio file received")
        raise HTTPException(status_code=400, detail="Empty audio file")

    audio_buffer = io.BytesIO(content)
    audio_buffer.name = file.filename or "audio.webm"

    model_name = _resolve_model_name()
    logger.info(f"Final model name: {model_name}")

    try:
        client = _get_client()
        logger.info("OpenAI client obtained, making transcription request...")
        
        transcription = client.audio.transcriptions.create(
            model=model_name,
            file=audio_buffer,
            response_format="text",
        )
        logger.info("Transcription request completed successfully")
        
    except OpenAIError as exc:
        logger.error(f"OpenAI API Error: {exc}")
        raise HTTPException(
            status_code=502,
            detail=f"Transcription failed: {exc}",
        ) from exc
    except Exception as exc:
        logger.error(f"Unexpected error during transcription: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {exc}",
        ) from exc

    text = _normalize_transcription_result(transcription)
    status = "success" if text else "empty"
    logger.info(f"Transcription result: {status}, length: {len(text)}")

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


@router.get("/debug/openai")
async def debug_openai():
    """
    Debug endpoint to check OpenAI configuration
    """
    debug_info = {
        "openai_api_key_set": bool(os.getenv("OPENAI_API_KEY")),
        "openai_api_key_length": len(os.getenv("OPENAI_API_KEY", "")),
        "openai_api_key_prefix": os.getenv("OPENAI_API_KEY", "")[:10] + "..." if os.getenv("OPENAI_API_KEY") else "None",
        "whisper_model": _resolve_model_name(),
        "whisper_env_vars": {key: os.getenv(key) for key in _WHISPER_ENV_KEYS}
    }
    
    try:
        client = _get_client()
        # Test with a simple request
        models = client.models.list()
        debug_info["openai_connection"] = "success"
        debug_info["models_available"] = len(models.data)
    except Exception as e:
        debug_info["openai_connection"] = f"failed: {e}"
    
    return debug_info
