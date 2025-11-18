# routes/assignments.py
# ==========================================================
# Routes for creating and retrieving assignments.
# Supports instructor authentication via JWT tokens.
# ==========================================================

import os
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select
from jose import jwt, JWTError
from datetime import datetime, timedelta

from db import get_session
from models import Assignment, User
from schemas import AssignmentCreate, AssignmentOut

# ----------------------------------------------------------
# Router setup
# ----------------------------------------------------------
router = APIRouter(prefix="/assignments", tags=["assignments"])

# ----------------------------------------------------------
# JWT Config (Render loads ENV vars correctly)
# ----------------------------------------------------------
SECRET_KEY = os.getenv("JWT_SECRET", "your-super-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


# ----------------------------------------------------------
# Helper: Extract authenticated user from JWT token
# ----------------------------------------------------------
def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.split(" ")[1]

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing user_id")

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Fetch the user from DB
    user = session.exec(select(User).where(User.id == user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


# ----------------------------------------------------------
# POST /assignments/
# Instructor creates new assignment
# ----------------------------------------------------------
@router.post("/", response_model=AssignmentOut)
def create_assignment(
    payload: AssignmentCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Instructor creates a new assignment."""

    data = payload.model_dump(exclude={"owner_id"}, exclude_none=True)

    assignment = Assignment(**data, owner_id=user.id)

    session.add(assignment)
    session.commit()
    session.refresh(assignment)

    return assignment


# ----------------------------------------------------------
# GET /assignments/{assignment_id}
# Public — students can load assignments
# ----------------------------------------------------------
@router.get("/{assignment_id}", response_model=AssignmentOut)
def get_assignment(assignment_id: str, session: Session = Depends(get_session)):
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment


# ----------------------------------------------------------
# GET /assignments/
# Instructor can view only their assignments
# ----------------------------------------------------------
@router.get("/", response_model=list[AssignmentOut])
def list_assignments(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    stmt = select(Assignment).where(Assignment.owner_id == user.id)
    return session.exec(stmt).all()


# ----------------------------------------------------------
# OPTIONAL: Manual token generation for debugging
# ----------------------------------------------------------
@router.post("/token")
def generate_token(email: str, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == email)).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": user.id, "exp": expire}
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return {"access_token": token, "token_type": "bearer"}
