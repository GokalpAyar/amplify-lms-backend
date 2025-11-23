# main.py
# FastAPI entry point configured for Supabase + Render/Railway deployment.

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlmodel import SQLModel

from db import engine
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

_default_allowed_origins = [
    "http://localhost:3000",
    "https://<YOUR_FRONTEND_DOMAIN>.vercel.app",
    "*",
]

_configured_origins = os.getenv("FRONTEND_ORIGINS")
if _configured_origins:
    parsed_origins = [origin.strip() for origin in _configured_origins.split(",") if origin.strip()]
    allow_origins = list(dict.fromkeys(parsed_origins + _default_allowed_origins))
else:
    allow_origins = _default_allowed_origins

cors_kwargs = {
    "allow_origins": allow_origins,
    "allow_credentials": False,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
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
    _ensure_response_aux_columns()


def _ensure_response_aux_columns() -> None:
    """Add optional columns to response table when missing (for legacy databases)."""
    try:
        with engine.begin() as connection:
            inspector = inspect(connection)
            columns = {column["name"] for column in inspector.get_columns("response")}
            migrations: dict[str, str] = {
                "audio_file_url": "VARCHAR",
                "student_accuracy_rating": "INTEGER",
                "student_rating_comment": "TEXT",
            }
            for column_name, column_type in migrations.items():
                if column_name in columns:
                    continue
                logger.info("Adding missing %s column to response table.", column_name)
                connection.execute(text(f"ALTER TABLE response ADD COLUMN {column_name} {column_type}"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unable to verify or add response optional columns: %s", exc)


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

