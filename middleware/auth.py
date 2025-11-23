"""Authentication helpers for extracting Clerk user IDs."""

from __future__ import annotations

import logging
import os
from typing import Any

from clerk_backend_api import verify_token
from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

_DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in {"1", "true", "yes", "on"}
__all__ = ["require_user_id", "get_optional_user_id"]


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
    user_id = _resolve_user_id(
        authorization,
        demo_user_override,
        clerk_session_token,
        clerk_user_id_header,
        raise_on_missing=True,
    )
    # Since raise_on_missing=True, user_id is guaranteed to be not None
    assert user_id is not None
    return user_id


def get_optional_user_id(
    authorization: str | None = Header(default=None, alias="Authorization"),
    demo_user_override: str | None = Header(default=None, alias="X-Demo-User-Id"),
    clerk_session_token: str | None = Header(default=None, alias="X-Clerk-Session-Token"),
    clerk_user_id_header: str | None = Header(default=None, alias="X-Clerk-User-Id"),
) -> str | None:
    """
    Resolve the current user's Clerk ID, returning None if missing.
    """
    return _resolve_user_id(
        authorization,
        demo_user_override,
        clerk_session_token,
        clerk_user_id_header,
        raise_on_missing=False,
    )


def _resolve_user_id(
    authorization: str | None,
    demo_user_override: str | None,
    clerk_session_token: str | None,
    clerk_user_id_header: str | None,
    raise_on_missing: bool,
) -> str | None:
    token: str | None = None
    if authorization:
        token = _extract_bearer_token(authorization)
    elif clerk_session_token:
        token = clerk_session_token.strip()

    if token:
        user_id = _verify_token_with_clerk(token)

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
        if raise_on_missing:
            raise _unauthorized(
                "Demo mode requires a Clerk token or an X-Clerk-User-Id / X-Demo-User-Id header.",
            )
        return None

    if raise_on_missing:
        raise _unauthorized("Missing Authorization header.")
    return None


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


def _verify_token_with_clerk(token: str) -> str:
    secret_key = os.getenv("CLERK_SECRET_KEY")
    if not secret_key:
        logger.error("CLERK_SECRET_KEY is not configured.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service not configured.",
        )

    try:
        payload: dict[str, Any] = verify_token(token, clerk_sk=secret_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Clerk token verification failed: %s", exc)
        raise _unauthorized("Invalid authentication token.") from exc

    user_id = payload.get("sub")
    if not user_id:
        logger.error("Clerk token payload missing 'sub': %s", payload)
        raise _unauthorized("Authentication token missing user identity.")
    return user_id
