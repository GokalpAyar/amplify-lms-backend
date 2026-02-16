import os
from fastapi import Header, HTTPException
from jose import jwt, JWTError

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
ALGORITHMS = ["HS256"]

def get_current_instructor(authorization: str = Header(None)):
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(status_code=500, detail="SUPABASE_JWT_SECRET is not set on the server")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization Bearer token")

    token = authorization.split(" ", 1)[1].strip()

    try:
        payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=ALGORITHMS)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing sub")

    return {"user_id": user_id, "payload": payload}

