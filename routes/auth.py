from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])


class ValidateKeyPayload(BaseModel):
    key: str


@router.post("/validate-key")
def validate_key(payload: ValidateKeyPayload):
    """
    Validate an admin key using the ADMIN_SECRET_KEY environment variable.
    """

    expected_key = os.getenv("ADMIN_SECRET_KEY")
    if expected_key is None:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_SECRET_KEY not configured on the server.",
        )

    return {"valid": payload.key == expected_key}
