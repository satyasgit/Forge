"""
Backend skill: FastAPI + SQLAlchemy production patterns.
Injected into BackendAgent context.
"""

REPOSITORY_PATTERN = '''
# repositories/user_repository.py
# Isolates DB queries from business logic. Makes testing trivial.

from sqlalchemy.orm import Session
from sqlalchemy import select, func
from models.user import User
from schemas.user import UserCreate, UserUpdate


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, user_id: str) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email))

    def list(self, skip: int = 0, limit: int = 50) -> tuple[list[User], int]:
        total = self.db.scalar(select(func.count()).select_from(User))
        users = self.db.scalars(select(User).offset(skip).limit(limit)).all()
        return list(users), total or 0

    def create(self, data: UserCreate, hashed_password: str) -> User:
        user = User(**data.model_dump(exclude={"password"}), hashed_password=hashed_password)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update(self, user: User, data: UserUpdate) -> User:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete(self, user: User) -> None:
        self.db.delete(user)
        self.db.commit()
'''

SERVICE_PATTERN = '''
# services/user_service.py
# Business logic layer. No direct DB access — uses repository.

from fastapi import HTTPException, status
from passlib.hash import argon2

from repositories.user_repository import UserRepository
from schemas.user import UserCreate, UserUpdate, UserResponse
from models.user import User


class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def get_or_404(self, user_id: str) -> User:
        user = self.repo.get(user_id)
        if not user:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        return user

    def create(self, data: UserCreate) -> User:
        if self.repo.get_by_email(data.email):
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
        hashed = argon2.hash(data.password)
        return self.repo.create(data, hashed)

    def authenticate(self, email: str, password: str) -> User:
        user = self.repo.get_by_email(email)
        if not user or not argon2.verify(password, user.hashed_password):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user
'''

FASTAPI_ROUTE_PATTERN = '''
# api/routes/users.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.auth import get_current_user
from repositories.user_repository import UserRepository
from services.user_service import UserService
from schemas.user import UserCreate, UserUpdate, UserResponse, PaginatedUsers
from models.user import User

router = APIRouter(prefix="/users", tags=["users"])


def get_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(UserRepository(db))


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get the authenticated user\'s profile."""
    return current_user


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: str,
    service: UserService = Depends(get_service),
    _: User = Depends(get_current_user),   # auth gate
):
    return service.get_or_404(user_id)


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, service: UserService = Depends(get_service)):
    return service.create(data)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    data: UserUpdate,
    service: UserService = Depends(get_service),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot modify another user")
    user = service.get_or_404(user_id)
    return service.repo.update(user, data)
'''

PYDANTIC_V2_PATTERNS = '''
# schemas/user.py — Pydantic v2

from pydantic import BaseModel, EmailStr, field_validator, model_validator
from datetime import datetime
from typing import Annotated
from pydantic import StringConstraints

PasswordStr = Annotated[str, StringConstraints(min_length=8, max_length=128)]


class UserCreate(BaseModel):
    email: EmailStr
    password: PasswordStr
    name: str

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name cannot be blank")
        return v.strip()


class UserUpdate(BaseModel):
    name: str | None = None
    avatar_url: str | None = None


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}   # replaces orm_mode=True in v1


class PaginatedUsers(BaseModel):
    items: list[UserResponse]
    total: int
    skip: int
    limit: int
'''

SQLALCHEMY_MODEL_PATTERN = '''
# models/user.py — SQLAlchemy 2.0 mapped classes

import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(),
                                                  onupdate=func.now(), nullable=False)

    # relationships
    # subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")
'''

JWT_AUTH_PATTERN = '''
# core/auth.py — JWT auth with refresh tokens

import os
from datetime import datetime, timedelta
from typing import Literal

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from core.database import get_db
from models.user import User

SECRET_KEY = os.environ["JWT_SECRET_KEY"]   # never hardcode
ALGORITHM = "HS256"
bearer = HTTPBearer()


def create_token(
    user_id: str,
    kind: Literal["access", "refresh"] = "access",
) -> str:
    expiry = timedelta(minutes=15) if kind == "access" else timedelta(days=7)
    payload = {
        "sub": user_id,
        "kind": kind,
        "exp": datetime.utcnow() + expiry,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    if payload.get("kind") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")

    user = db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user
'''

API_ERROR_HANDLING = '''
# core/exceptions.py — global error handlers

from fastapi import Request, FastAPI
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI):

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(PermissionError)
    async def permission_error_handler(request: Request, exc: PermissionError):
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    @app.exception_handler(Exception)
    async def generic_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled error on {request.method} {request.url}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},  # never expose exc in production
        )
'''
