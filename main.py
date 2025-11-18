# main.py
# FastAPI entry point configured for Supabase + Render/Railway deployment.

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import assignments, responses, speech, users

_BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=_BASE_DIR / ".env")


def _cors_origins() -> list[str]:
    """Compute CORS allowlist from environment variables."""

    env_value = os.getenv("FRONTEND_ORIGINS")
    if env_value:
        parsed = [origin.strip().rstrip("/") for origin in env_value.split(",") if origin.strip()]
        if parsed:
            return parsed

    defaults = {"http://localhost:5173", "https://localhost:5173"}
    vercel_url = os.getenv("VERCEL_URL")
    if vercel_url:
        formatted = vercel_url if vercel_url.startswith("http") else f"https://{vercel_url}"
        defaults.add(formatted.rstrip("/"))
    return sorted(defaults)


app = FastAPI(
    title="Amplify LMS Backend",
    description="AI-Powered Learning Management System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=os.getenv("FRONTEND_ORIGIN_REGEX"),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(assignments.router)
app.include_router(responses.router)
app.include_router(speech.router)


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

