# routes/users.py
# ==========================================================
# Handles user registration, login (JWT auth), and profile.
# Supports instructor authentication for Amplify-LMS.
# ==========================================================

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import ValidationError
from sqlmodel import Session, select

from datetime import datetime, timedelta
import os

from db import get_session
from models import User, UserCreate, UserLogin
from schemas import UserBase

router = APIRouter(prefix="/users", tags=["users"])

SECRET_KEY = os.getenv("JWT_SECRET", "your-super-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ----------------------------------------------------------
# REGISTER USER
# ----------------------------------------------------------
async def _extract_user_data(request: Request) -> dict:
    data = {}
    content_type = (request.headers.get("content-type") or "").lower()

    if "application/json" in content_type:
        try:
            body = await request.json()
            if isinstance(body, dict):
                data.update(body)
            else:
                raise HTTPException(status_code=400, detail="Invalid JSON payload")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
    elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        for key, value in form.multi_items():
            if isinstance(value, str):
                data[key] = value
    if not data:
        for key, value in request.query_params.multi_items():
            data[key] = value
    return data


def _validate_user_payload(model_cls, data: dict):
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc

@router.post("/register", response_model=UserBase, status_code=status.HTTP_201_CREATED)
async def register_user(
    request: Request,
    session: Session = Depends(get_session),
):
    payload = _validate_user_payload(UserCreate, await _extract_user_data(request))
    email = payload.email.strip().lower()
    # Check existing user
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    # IMPORTANT: Hash the password!
    password_hash = get_password_hash(payload.password)
    user = User(
        name=payload.name.strip() if payload.name else None,
        email=email,
        password_hash=password_hash,
        role="instructor",
    )

    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# ----------------------------------------------------------
# LOGIN
# ----------------------------------------------------------
@router.post("/login")
async def login_user(
    request: Request,
    session: Session = Depends(get_session),
):
    payload = _validate_user_payload(UserLogin, await _extract_user_data(request))
    email = payload.email.strip().lower()
    user = session.exec(select(User).where(User.email == email)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token({"sub": user.id})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
        },
    }
