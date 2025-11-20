# main.py
# FastAPI entry point configured for Supabase + Render/Railway deployment.

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel

from db import engine
from audio_storage import AudioStorageError, try_get_audio_storage
from routes import assignments, auth, responses, speech

_BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=_BASE_DIR / ".env")

DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in {"1", "true", "yes", "on"}

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Amplify LMS Backend",
    description="AI-Powered Learning Management System",
    version="1.0.0",
)

cors_kwargs = {
    "allow_origins": ["*"] if DEMO_MODE else ["*"],
    "allow_credentials": False,
    "allow_methods": ["*"] if DEMO_MODE else ["*"],
    "allow_headers": ["*"] if DEMO_MODE else ["*"],
}

app.add_middleware(
    CORSMiddleware,
    **cors_kwargs,
)

app.include_router(auth.router)
app.include_router(assignments.router)
app.include_router(responses.router)
app.include_router(speech.router)

if not DEMO_MODE:
    from routes import users  # imported lazily to avoid unused dependency in demo mode

    app.include_router(users.router)


@app.on_event("startup")
def init_database() -> None:
    """Ensure tables and columns exist before serving traffic."""
    logger.info("Ensuring SQLModel metadata is up to date (demo_mode=%s)", DEMO_MODE)
    SQLModel.metadata.create_all(engine)

    storage = try_get_audio_storage()
    if storage:
        try:
            storage.ensure_bucket()
            logger.info("Supabase audio bucket verified.")
        except AudioStorageError as exc:
            logger.warning("Supabase audio bucket check failed: %s", exc)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {
        "status": "Backend Live!",
        "message": "Amplify LMS API running.",
        "docs": "/docs",
    }

