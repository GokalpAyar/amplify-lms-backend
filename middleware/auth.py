"""Authentication helpers for extracting Clerk user IDs."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

import httpx
from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

_DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in {"1", "true", "yes", "on"}
_REQUEST_TIMEOUT = float(os.getenv("CLERK_HTTP_TIMEOUT", "5.0"))

__all__ = ["require_user_id"]


def require_user_id(
    authorization: str | None = Header(default=None, alias="Authorization"),
    demo_user_override: str | None = Header(default=None, alias="X-Demo-User-Id"),
    clerk_session_token: str | None = Header(default=None, alias="X-Clerk-Session-Token"),
    clerk_user_id_header: str | None = Header(default=None, alias="X-Clerk-User-Id"),
) -> str:
    """
    Resolve the current user's Clerk ID.

    In production we expect a standard `Authorization: Bearer <token>` header.
    While DEMO_MODE is enabled we allow overriding the user via the optional
    `X-Demo-User-Id` header (or `DEMO_USER_ID` env var) to keep local testing easy.
    """

    token: str | None = None
    if authorization:
        token = _extract_bearer_token(authorization)
    elif clerk_session_token:
        token = clerk_session_token.strip()

    if token:
        claims = _verify_token_with_clerk(token)
        user_id = (
            claims.get("sub")
            or claims.get("user_id")
            or claims.get("userId")
            or claims.get("uid")
        )
        if not user_id:
            logger.error("Clerk claims missing `sub` and `user_id`: %s", claims)
            raise _unauthorized("Authentication token missing user identity.")

        if clerk_user_id_header and clerk_user_id_header != user_id:
            logger.warning(
                "Clerk user id header '%s' does not match token subject '%s'. "
                "Proceeding with the token value.",
                clerk_user_id_header,
                user_id,
            )
        return user_id

    if _DEMO_MODE:
        fallback = (
            clerk_user_id_header
            or demo_user_override
            or os.getenv("DEMO_USER_ID")
        )
        if fallback:
            logger.debug("DEMO_MODE active — using fallback user id '%s'.", fallback)
            return fallback
        raise _unauthorized(
            "Demo mode requires a Clerk token or an X-Clerk-User-Id / X-Demo-User-Id header.",
        )

    raise _unauthorized("Missing Authorization header.")


def _extract_bearer_token(authorization_header: str) -> str:
    parts = authorization_header.strip().split(" ", maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise _unauthorized("Authorization header must be in the format 'Bearer <token>'.")
    return parts[1].strip()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _verify_token_with_clerk(token: str) -> dict[str, Any]:
    secret_key = os.getenv("CLERK_SECRET_KEY")
    if not secret_key:
        logger.error("CLERK_SECRET_KEY is not configured.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service not configured.",
        )

    verify_url = _clerk_verify_url()
    try:
        response = httpx.post(
            verify_url,
            headers={"Authorization": f"Bearer {secret_key}"},
            json={"token": token},
            timeout=_REQUEST_TIMEOUT,
        )
    except httpx.RequestError as exc:
        logger.exception("Unable to contact Clerk while verifying token.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify authentication token right now.",
        ) from exc

    if response.status_code != 200:
        error_message = "Invalid Clerk session token."
        try:
            payload = response.json()
            error_message = (
                payload.get("error", {}).get("message")
                or payload.get("message")
                or error_message
            )
        except ValueError:
            payload = None
        logger.warning("Clerk token verification failed: %s", error_message)
        raise _unauthorized("Invalid authentication token.")

    try:
        payload = response.json()
    except ValueError as exc:
        logger.exception("Clerk verification endpoint returned invalid JSON.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service returned invalid response.",
        ) from exc

    data = payload.get("data", payload)
    claims = data.get("claims") or data.get("session", {}).get("claims")
    if not claims:
        logger.error("Clerk verification response missing claims: %s", payload)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service response missing claims.",
        )
    return claims


@lru_cache(maxsize=1)
def _clerk_verify_url() -> str:
    base_url = os.getenv("CLERK_API_BASE_URL", "https://api.clerk.dev")
    return f"{base_url.rstrip('/')}/v1/tokens/verify"
