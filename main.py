# main.py
# FastAPI entry point configured for Supabase + Render deployment.

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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in {"1", "true", "yes", "on"}

app = FastAPI(
    title="Amplify LMS Backend",
    description="AI-Powered Learning Management System",
    version="1.0.0",
)

# -------------------------------------------------------------------
# CORS (IMPORTANT for Vercel + Supabase Bearer-token auth)
# -------------------------------------------------------------------
# Render env examples:
# FRONTEND_ORIGINS=https://amplify-lms-frontend.vercel.app,http://localhost:5173,http://localhost:3000
# FRONTEND_ORIGIN=https://amplify-lms-frontend.vercel.app
# FRONTEND_ORIGIN_REGEX=https://.*\.vercel\.app
#
# IMPORTANT:
# - no quotes
# - no trailing slash
#
FRONTEND_ORIGINS = os.getenv(
    "FRONTEND_ORIGINS",
    "https://amplify-lms-frontend.vercel.app,http://localhost:5173,http://localhost:3000",
)
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "").strip()
FRONTEND_ORIGIN_REGEX = os.getenv("FRONTEND_ORIGIN_REGEX", "").strip()

allowed_origins = [o.strip() for o in FRONTEND_ORIGINS.split(",") if o.strip()]
if FRONTEND_ORIGIN and FRONTEND_ORIGIN not in allowed_origins:
    allowed_origins.append(FRONTEND_ORIGIN)

logger.info("CORS allowed origins: %s", allowed_origins)
logger.info(
    "CORS allowed origin regex: %s",
    FRONTEND_ORIGIN_REGEX if FRONTEND_ORIGIN_REGEX else "(none)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=FRONTEND_ORIGIN_REGEX or None,
    allow_credentials=False,  # Bearer token auth, not cookie auth
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------
# Routers
# -------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(assignments.router)
app.include_router(responses.router)
app.include_router(speech.router)

# Keep old users auth during transition (recommended).
# Remove later after Supabase login is fully tested end-to-end.
if not DEMO_MODE:
    from routes import users  # imported lazily to avoid unused dependency in demo mode

    app.include_router(users.router)

# -------------------------------------------------------------------
# Startup
# -------------------------------------------------------------------
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

            # NOTE: Your new tables are likely named 'responses' not 'response'.
            # This migration is only for legacy installs.
            table_name = "response"
            try:
                columns = {column["name"] for column in inspector.get_columns(table_name)}
            except Exception:
                # If legacy table doesn't exist, skip quietly.
                return

            migrations: dict[str, str] = {
                "audio_file_url": "VARCHAR",
                "student_accuracy_rating": "INTEGER",
                "student_rating_comment": "TEXT",
            }
            for column_name, column_type in migrations.items():
                if column_name in columns:
                    continue
                logger.info("Adding missing %s column to %s table.", column_name, table_name)
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unable to verify or add legacy response optional columns: %s", exc)


# -------------------------------------------------------------------
# Health / Root
# -------------------------------------------------------------------
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