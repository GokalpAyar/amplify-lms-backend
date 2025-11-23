"""
Shared authentication helpers for resolving the current user from Clerk or demo headers.
"""

from __future__ import annotations

import logging
import os
from typing import Final

import requests
from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

_TRUE_VALUES: Final[set[str]] = {"1", "true", "yes", "on"}
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in _TRUE_VALUES

CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")
CLERK_API_BASE_URL = os.getenv("CLERK_API_BASE_URL", "https://api.clerk.com").rstrip("/")
CLERK_API_VERSION = os.getenv("CLERK_API_VERSION", "2024-09-17")
CLERK_VERIFY_PATH = "/v1/sessions/verify"
CLERK_TIMEOUT_SECONDS = float(os.getenv("CLERK_VERIFY_TIMEOUT", "5"))

_LEGACY_HEADER_KEYS: Final[tuple[str, ...]] = (
    "x-clerk-user-id",
    "x-user-id",
    "x-owner-id",
    "x-demo-user",
)


class AuthenticationError(Exception):
    """Raised when the backend cannot determine the calling user."""


def get_authenticated_user_id(request: Request) -> str:
    """
    Resolve the current user's Clerk ID.

    - Prefer explicit headers (X-Clerk-User-Id, X-User-Id, etc.) for local/dev usage.
    - Fallback to verifying a Clerk session token from the Authorization header.
    - In demo mode only, an `owner_id` query parameter keeps older clients working.
    """

    try:
        return _resolve_user_id(request)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


def _resolve_user_id(request: Request) -> str:
    explicit_header_user = _first_present_header(request)
    if explicit_header_user:
        return explicit_header_user

    bearer_token = _extract_bearer_token(request.headers.get("authorization"))
    if bearer_token:
        return _verify_clerk_session(bearer_token)

    if DEMO_MODE:
        legacy_param = request.query_params.get("owner_id")
        if legacy_param:
            return legacy_param

    raise AuthenticationError(
        "Authentication required. Provide a Clerk session token or X-User-Id header.",
    )


def _first_present_header(request: Request) -> str | None:
    for header_key in _LEGACY_HEADER_KEYS:
        header_value = request.headers.get(header_key)
        if header_value:
            return header_value
    return None


def _extract_bearer_token(auth_header: str | None) -> str | None:
    if not auth_header:
        return None

    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def _verify_clerk_session(token: str) -> str:
    if not CLERK_SECRET_KEY:
        raise AuthenticationError(
            "Server missing CLERK_SECRET_KEY; cannot verify Clerk tokens.",
        )

    url = f"{CLERK_API_BASE_URL}{CLERK_VERIFY_PATH}"
    headers = {
        "Authorization": f"Bearer {CLERK_SECRET_KEY}",
        "Content-Type": "application/json",
        "Clerk-Version": CLERK_API_VERSION,
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json={"token": token},
            timeout=CLERK_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning("Failed to reach Clerk for session verification: %s", exc)
        raise AuthenticationError("Unable to verify Clerk session right now.") from exc

    if response.status_code != 200:
        logger.info(
            "Clerk session verification failed with status %s: %s",
            response.status_code,
            response.text,
        )
        raise AuthenticationError("Invalid or expired authentication token.")

    data: dict[str, str | None] = response.json()
    user_id = data.get("user_id")
    if not user_id:
        logger.error("Clerk verification response missing user_id: %s", data)
        raise AuthenticationError("Authentication token missing user context.")

    return user_id


__all__ = ["get_authenticated_user_id"]
