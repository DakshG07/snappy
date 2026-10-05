from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session, joinedload

from .config import settings
from .db import get_db
from .models import AuthSession, User


SESSION_COOKIE = "scanny_session"
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
password_hasher = PasswordHasher()
DUMMY_PASSWORD_HASH = password_hasher.hash("scanny-timing-placeholder")


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return normalized


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def hash_session_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: User) -> str:
    now = datetime.now(timezone.utc)
    db.query(AuthSession).filter(AuthSession.expires_at <= now).delete(synchronize_session=False)
    raw_token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_session_token(raw_token),
            expires_at=now + timedelta(days=settings.session_days),
        )
    )
    return raw_token


def set_session_cookie(response: Response, raw_token: str) -> None:
    max_age = settings.session_days * 24 * 60 * 60
    response.set_cookie(
        key=SESSION_COOKIE,
        value=raw_token,
        max_age=max_age,
        expires=datetime.now(timezone.utc) + timedelta(days=settings.session_days),
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def get_current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> User:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    auth_session = (
        db.query(AuthSession)
        .options(joinedload(AuthSession.user))
        .filter(
            AuthSession.token_hash == hash_session_token(session_token),
            AuthSession.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )
    if auth_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return auth_session.user
