from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import (
    SESSION_COOKIE,
    DUMMY_PASSWORD_HASH,
    clear_session_cookie,
    create_session,
    get_current_user,
    hash_password,
    hash_session_token,
    normalize_email,
    set_session_cookie,
    verify_password,
)
from ..constants import REVIEW_CATEGORY_NAME
from ..db import LEGACY_USER_EMAIL, get_db
from ..models import AuthSession, Category, Document, User
from ..schemas import AuthCredentials, RegistrationCredentials, UserRead


router = APIRouter(prefix="/auth", tags=["auth"])


def _ensure_unsure(db: Session, user_id: int) -> None:
    unsure = (
        db.query(Category)
        .filter(Category.user_id == user_id, Category.is_system.is_(True))
        .first()
    )
    if unsure is None:
        db.add(Category(name=REVIEW_CATEGORY_NAME, is_system=True, user_id=user_id))


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegistrationCredentials,
    response: Response,
    db: Session = Depends(get_db),
) -> UserRead:
    email = normalize_email(payload.email)
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with that email already exists.")

    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with that email already exists.") from exc

    legacy_user = db.query(User).filter(User.email == LEGACY_USER_EMAIL).first()
    real_user_count = db.query(User).filter(User.email != LEGACY_USER_EMAIL, User.id != user.id).count()
    if legacy_user is not None and real_user_count == 0:
        db.query(Category).filter(Category.user_id == legacy_user.id).update(
            {Category.user_id: user.id}, synchronize_session=False
        )
        db.query(Document).filter(Document.user_id == legacy_user.id).update(
            {Document.user_id: user.id}, synchronize_session=False
        )
        db.delete(legacy_user)
    _ensure_unsure(db, user.id)
    raw_token = create_session(db, user)
    db.commit()
    set_session_cookie(response, raw_token)
    return UserRead.model_validate(user)


@router.post("/login", response_model=UserRead)
def login(
    payload: AuthCredentials,
    response: Response,
    db: Session = Depends(get_db),
) -> UserRead:
    try:
        email = normalize_email(payload.email)
    except HTTPException:
        verify_password(DUMMY_PASSWORD_HASH, payload.password)
        raise HTTPException(status_code=401, detail="Invalid email or password.") from None
    user = db.query(User).filter(User.email == email, User.email != LEGACY_USER_EMAIL).first()
    password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_valid = verify_password(password_hash, payload.password)
    if user is None or not password_valid:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    raw_token = create_session(db, user)
    db.commit()
    set_session_cookie(response, raw_token)
    return UserRead.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> None:
    if session_token:
        db.query(AuthSession).filter(
            AuthSession.token_hash == hash_session_token(session_token)
        ).delete(synchronize_session=False)
        db.commit()
    clear_session_cookie(response)


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)
