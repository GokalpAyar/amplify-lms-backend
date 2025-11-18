"""Expose the FastAPI app for Vercel's Python runtime."""

from __future__ import annotations

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from main import app  # noqa: E402  (import after sys.path adjustment)

__all__ = ["app"]
