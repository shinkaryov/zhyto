"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, field_validator

from src.auth.auth_service import (
    AuthIdentity,
    authenticate_credentials,
    get_current_identity,
    issue_access_token,
    list_secret_questions,
    normalize_email,
    register_whitelisted_user_with_secret,
    reset_password_with_secret_question,
)
from src.utils.config import settings
from src.utils import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Email/password login payload."""

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if not normalized or "@" not in normalized:
            raise ValueError("Invalid email format.")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Password cannot be empty.")
        return value


class AuthUserResponse(BaseModel):
    email: str
    user_id: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserResponse


class RegisterRequest(BaseModel):
    """Whitelist user self-registration payload."""

    email: str
    password: str
    confirm_password: str
    secret_question_id: str
    secret_answer: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if not normalized or "@" not in normalized:
            raise ValueError("Invalid email format.")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        min_len = max(6, int(settings.auth_password_min_length or 0))
        if not value or len(value) < min_len:
            raise ValueError(f"Password must be at least {min_len} characters long.")
        return value

    @field_validator("confirm_password")
    @classmethod
    def validate_confirm_password(cls, value: str) -> str:
        if not value:
            raise ValueError("Password confirmation cannot be empty.")
        return value

    @field_validator("secret_question_id")
    @classmethod
    def validate_secret_question_id(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("Secret question is required.")
        return cleaned

    @field_validator("secret_answer")
    @classmethod
    def validate_secret_answer(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("Secret answer cannot be empty.")
        return cleaned


class SecretQuestionResponse(BaseModel):
    id: str
    question: str


class ResetPasswordRequest(BaseModel):
    email: str
    secret_question_id: str
    secret_answer: str
    new_password: str
    confirm_password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if not normalized or "@" not in normalized:
            raise ValueError("Invalid email format.")
        return normalized

    @field_validator("secret_question_id")
    @classmethod
    def validate_secret_question_id(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("Secret question is required.")
        return cleaned

    @field_validator("secret_answer")
    @classmethod
    def validate_secret_answer(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("Secret answer cannot be empty.")
        return cleaned

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        min_len = max(6, int(settings.auth_password_min_length or 0))
        if not value or len(value) < min_len:
            raise ValueError(f"Password must be at least {min_len} characters long.")
        return value

    @field_validator("confirm_password")
    @classmethod
    def validate_confirm_password(cls, value: str) -> str:
        if not value:
            raise ValueError("Password confirmation cannot be empty.")
        return value


class ResetPasswordResponse(BaseModel):
    success: bool
    message: str


def _login_response_for_identity(identity: AuthIdentity) -> LoginResponse:
    access_token = issue_access_token(identity)
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=AuthUserResponse(email=identity.email, user_id=identity.user_id),
    )


@router.post("/register", response_model=LoginResponse)
async def register(payload: RegisterRequest) -> LoginResponse:
    """Allow whitelisted users to create their own password."""
    try:
        if payload.password != payload.confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match.")

        identity = await run_in_threadpool(
            register_whitelisted_user_with_secret,
            payload.email,
            payload.password,
            secret_question_id=payload.secret_question_id,
            secret_answer=payload.secret_answer,
        )
        return await run_in_threadpool(_login_response_for_identity, identity)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Registration failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Registration failed.") from exc


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    """Authenticate by email/password, then return bearer token."""
    try:
        identity = await run_in_threadpool(
            authenticate_credentials,
            payload.email,
            payload.password,
        )
        return await run_in_threadpool(_login_response_for_identity, identity)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Login failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Login failed.") from exc


@router.get("/secret-questions", response_model=list[SecretQuestionResponse])
async def secret_questions() -> list[SecretQuestionResponse]:
    """Return available secret questions for registration/password reset."""
    try:
        return await run_in_threadpool(list_secret_questions)
    except Exception as exc:
        logger.error("Failed to load secret questions: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to load secret questions."
        ) from exc


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(payload: ResetPasswordRequest) -> ResetPasswordResponse:
    """Reset password by email + secret question (beta flow without emails)."""
    try:
        if payload.new_password != payload.confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match.")
        await run_in_threadpool(
            reset_password_with_secret_question,
            email=payload.email,
            secret_question_id=payload.secret_question_id,
            secret_answer=payload.secret_answer,
            new_password=payload.new_password,
        )
        return ResetPasswordResponse(
            success=True,
            message="Password reset successful. You can now log in.",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Password reset failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Password reset failed.") from exc


@router.get("/me", response_model=AuthUserResponse)
async def me(
    current_user: AuthIdentity = Depends(get_current_identity),
) -> AuthUserResponse:
    """Return current authenticated profile."""
    return AuthUserResponse(
        email=current_user.email,
        user_id=current_user.user_id,
    )
