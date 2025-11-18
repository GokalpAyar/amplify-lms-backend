# db.py
# Centralized database engine/session setup for Supabase PostgreSQL.

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlmodel import Session, create_engine


_BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=_BASE_DIR / ".env")

_SQLITE_PATH = _BASE_DIR / "amplify.db"

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Local fallback keeps developer experience simple while production uses DATABASE_URL.
    DATABASE_URL = f"sqlite:///{_SQLITE_PATH}"
    # Mirror the computed value for any downstream code that reads directly from the environment.
    os.environ.setdefault("DATABASE_URL", DATABASE_URL)

engine_config: dict[str, object] = {
    "echo": False,
    "pool_pre_ping": True,
}

if DATABASE_URL.startswith("sqlite"):
    engine_config["connect_args"] = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    **engine_config,
)


def get_session():
    """Provide a scoped SQLModel session for each request."""
    with Session(engine) as session:
        yield session
