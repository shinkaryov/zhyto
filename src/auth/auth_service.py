"""Simple auth service for email/password login with whitelist enforcement."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.db.cosmos_client import get_cosmos_client
from src.utils.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthIdentity:
    """Authenticated identity resolved from login or bearer token."""

    email: str
    user_id: str


SECRET_QUESTIONS: tuple[tuple[str, str], ...] = (
    ("favorite_asset", "What is your favourite asset?"),
    ("first_asset", "What was your first investment asset ever?"),
    ("favorite_company", "What company stock do you follow most?"),
    ("first_broker", "What was the first broker/app you used for investing?"),
    ("risk_profile_word", "Which one word best describes your risk style?"),
    ("dream_market", "Which market interests you the most right now?"),
    ("first_investment_goal", "What was your first investment goal?"),
)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def normalize_secret_answer(answer: str) -> str:
    collapsed = " ".join((answer or "").strip().split())
    return collapsed.lower()


def email_to_user_id(email: str) -> str:
    normalized = normalize_email(email)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"user_{digest[:24]}"


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _urlsafe_b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def load_allowed_emails() -> set[str]:
    """Load allowed email list from configured whitelist file."""
    path = Path(settings.auth_email_whitelist_file)
    if not path.is_absolute():
        project_root = Path(__file__).resolve().parents[2]
        path = project_root / path
    if not path.exists():
        logger.warning("Auth whitelist file not found at '%s'", path)
        return set()

    allowed: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            cleaned = normalize_email(line)
            if cleaned and not cleaned.startswith("#"):
                allowed.add(cleaned)
    except Exception:
        logger.error("Failed to load auth whitelist file '%s'", path, exc_info=True)
        return set()
    return allowed


def _is_email_allowed(email: str) -> bool:
    return normalize_email(email) in load_allowed_emails()


def _validate_password_policy(password: str) -> None:
    min_length = max(6, int(settings.auth_password_min_length or 0))
    if not password or len(password) < min_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {min_length} characters long.",
        )


def _pbkdf2_iterations(value: Optional[int] = None) -> int:
    base = value if value is not None else settings.auth_password_pbkdf2_iterations
    return max(100000, int(base or 0))


def _hash_password(password: str, salt: bytes, iterations: int) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        (password or "").encode("utf-8"),
        salt,
        iterations,
    )
    return digest.hex()


def _verify_password(
    password: str,
    *,
    expected_hash: str,
    salt_b64: str,
    iterations: Optional[int] = None,
) -> bool:
    try:
        salt = _urlsafe_b64decode(salt_b64)
    except Exception:
        return False

    candidate = _hash_password(
        password,
        salt=salt,
        iterations=_pbkdf2_iterations(iterations),
    )
    return hmac.compare_digest(candidate, expected_hash or "")


def register_whitelisted_user(email: str, password: str) -> AuthIdentity:
    """Create first password for a whitelisted email."""
    normalized_email = normalize_email(email)
    if not normalized_email or not _is_email_allowed(normalized_email):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This email is not allowed.",
        )

    _validate_password_policy(password)
    identity = AuthIdentity(
        email=normalized_email,
        user_id=email_to_user_id(normalized_email),
    )

    client = get_cosmos_client()
    existing = client.get_user(identity.user_id) or {}
    existing_hash = str(existing.get("password_hash") or "").strip()
    existing_salt = str(existing.get("password_salt") or "").strip()
    if existing_hash and existing_salt:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Password is already set. Please log in.",
        )

    iterations = _pbkdf2_iterations()
    salt = os.urandom(16)
    now_iso = datetime.now(timezone.utc).isoformat()
    user_record = dict(existing)
    user_record["id"] = identity.user_id
    user_record["user_id"] = identity.user_id
    user_record["email"] = identity.email
    user_record["password_hash"] = _hash_password(
        password, salt=salt, iterations=iterations
    )
    user_record["password_salt"] = _urlsafe_b64encode(salt)
    user_record["password_algo"] = "pbkdf2_sha256"
    user_record["password_iterations"] = iterations
    user_record["password_updated_at"] = now_iso
    if not user_record.get("created_at"):
        user_record["created_at"] = now_iso

    client.upsert_user(user_record)
    return identity


def list_secret_questions() -> list[dict[str, str]]:
    return [{"id": item[0], "question": item[1]} for item in SECRET_QUESTIONS]


def _is_valid_secret_question_id(question_id: str) -> bool:
    candidate = str(question_id or "").strip()
    return any(candidate == item[0] for item in SECRET_QUESTIONS)


def _store_secret_answer(
    user_record: dict[str, object],
    *,
    question_id: str,
    answer: str,
) -> None:
    normalized_answer = normalize_secret_answer(answer)
    if not normalized_answer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Secret answer cannot be empty.",
        )
    if not _is_valid_secret_question_id(question_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid secret question.",
        )

    secret_iterations = _pbkdf2_iterations()
    secret_salt = os.urandom(16)
    user_record["secret_question_id"] = question_id
    user_record["secret_answer_hash"] = _hash_password(
        normalized_answer,
        salt=secret_salt,
        iterations=secret_iterations,
    )
    user_record["secret_answer_salt"] = _urlsafe_b64encode(secret_salt)
    user_record["secret_answer_iterations"] = secret_iterations


def _verify_secret_answer(
    user_record: dict[str, object],
    *,
    question_id: str,
    answer: str,
) -> bool:
    stored_question = str(user_record.get("secret_question_id") or "").strip()
    stored_hash = str(user_record.get("secret_answer_hash") or "").strip()
    stored_salt = str(user_record.get("secret_answer_salt") or "").strip()
    iterations = user_record.get("secret_answer_iterations")
    if not stored_question or not stored_hash or not stored_salt:
        return False
    if stored_question != str(question_id or "").strip():
        return False

    normalized_answer = normalize_secret_answer(answer)
    if not normalized_answer:
        return False
    return _verify_password(
        normalized_answer,
        expected_hash=stored_hash,
        salt_b64=stored_salt,
        iterations=int(iterations) if str(iterations or "").isdigit() else None,
    )


def register_whitelisted_user_with_secret(
    email: str,
    password: str,
    *,
    secret_question_id: str,
    secret_answer: str,
) -> AuthIdentity:
    identity = register_whitelisted_user(email, password)
    client = get_cosmos_client()
    user_record = client.get_user(identity.user_id) or {}
    _store_secret_answer(
        user_record,
        question_id=secret_question_id,
        answer=secret_answer,
    )
    user_record["id"] = identity.user_id
    user_record["user_id"] = identity.user_id
    user_record["email"] = identity.email
    user_record["secret_answer_updated_at"] = datetime.now(timezone.utc).isoformat()
    client.upsert_user(user_record)
    return identity


def reset_password_with_secret_question(
    *,
    email: str,
    secret_question_id: str,
    secret_answer: str,
    new_password: str,
) -> None:
    normalized_email = normalize_email(email)
    if not normalized_email or not _is_email_allowed(normalized_email):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid reset credentials.",
        )
    if not _is_valid_secret_question_id(secret_question_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid secret question.",
        )
    _validate_password_policy(new_password)

    identity = AuthIdentity(
        email=normalized_email,
        user_id=email_to_user_id(normalized_email),
    )
    client = get_cosmos_client()
    user_record = client.get_user(identity.user_id)
    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found.",
        )

    has_secret_configured = all(
        str(user_record.get(field) or "").strip()
        for field in ("secret_question_id", "secret_answer_hash", "secret_answer_salt")
    )
    if has_secret_configured:
        if not _verify_secret_answer(
            user_record,
            question_id=secret_question_id,
            answer=secret_answer,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid reset credentials.",
            )
    else:
        # Safe bootstrap migration path for legacy beta users created before secret questions.
        logger.warning(
            "Applying legacy password-reset bootstrap for user_id=%s (no secret question configured)",
            identity.user_id,
        )
        _store_secret_answer(
            user_record,
            question_id=secret_question_id,
            answer=secret_answer,
        )
        user_record["secret_answer_updated_at"] = datetime.now(timezone.utc).isoformat()

    iterations = _pbkdf2_iterations()
    salt = os.urandom(16)
    user_record["password_hash"] = _hash_password(
        new_password,
        salt=salt,
        iterations=iterations,
    )
    user_record["password_salt"] = _urlsafe_b64encode(salt)
    user_record["password_algo"] = "pbkdf2_sha256"
    user_record["password_iterations"] = iterations
    user_record["password_updated_at"] = datetime.now(timezone.utc).isoformat()
    client.upsert_user(user_record)


def _build_token_payload(identity: AuthIdentity) -> dict[str, object]:
    ttl_minutes = max(5, int(settings.auth_token_ttl_minutes or 0))
    exp = int(time.time()) + ttl_minutes * 60
    return {
        "email": identity.email,
        "uid": identity.user_id,
        "exp": exp,
    }


def issue_access_token(identity: AuthIdentity) -> str:
    """Issue signed opaque token."""
    secret = (settings.auth_token_secret or "").encode("utf-8")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth token secret is not configured.",
        )

    payload_raw = json.dumps(
        _build_token_payload(identity), separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    payload_part = _urlsafe_b64encode(payload_raw)
    signature = hmac.new(secret, payload_part.encode("utf-8"), hashlib.sha256).digest()
    signature_part = _urlsafe_b64encode(signature)
    return f"{payload_part}.{signature_part}"


def decode_access_token(token: str) -> AuthIdentity:
    """Decode and validate token; raise 401 for invalid token."""
    secret = (settings.auth_token_secret or "").encode("utf-8")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth token secret is not configured.",
        )

    try:
        payload_part, signature_part = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        ) from exc

    expected_signature = _urlsafe_b64encode(
        hmac.new(secret, payload_part.encode("utf-8"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(signature_part, expected_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token signature.",
        )

    try:
        payload = json.loads(_urlsafe_b64decode(payload_part).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token payload.",
        ) from exc

    email = normalize_email(str(payload.get("email") or ""))
    user_id = str(payload.get("uid") or "").strip()
    exp = int(payload.get("exp") or 0)

    if not email or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is malformed.",
        )
    if exp <= int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token expired.",
        )

    return AuthIdentity(email=email, user_id=user_id)


def authenticate_credentials(email: str, password: str) -> AuthIdentity:
    """Validate email/password against whitelist and per-user password record."""
    normalized_email = normalize_email(email)
    if not normalized_email or not _is_email_allowed(normalized_email):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    identity = AuthIdentity(
        email=normalized_email,
        user_id=email_to_user_id(normalized_email),
    )
    client = get_cosmos_client()
    user_record = client.get_user(identity.user_id)
    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password is not set for this email. Create a password first.",
        )

    expected_hash = str(user_record.get("password_hash") or "").strip()
    salt_b64 = str(user_record.get("password_salt") or "").strip()
    iterations = user_record.get("password_iterations")
    if not expected_hash or not salt_b64:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password is not set for this email. Create a password first.",
        )

    if not _verify_password(
        password,
        expected_hash=expected_hash,
        salt_b64=salt_b64,
        iterations=int(iterations) if str(iterations or "").isdigit() else None,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    return identity


def get_current_identity(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> AuthIdentity:
    """FastAPI dependency returning authenticated identity."""
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return decode_access_token(credentials.credentials)
