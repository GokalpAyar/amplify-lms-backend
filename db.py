# db.py
# Centralized database engine/session setup for Supabase PostgreSQL.

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlmodel import Session, create_engine


_BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=_BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Set DATABASE_URL to your database connection string before starting the API.",
    )

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
