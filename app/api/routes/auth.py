"""Register, log in and fetch the logged-in user."""
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.core.security import (
    DUMMY_HASH,
    SESSION_COOKIE,
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from app.models.session import UserSession
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserRead

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: DbSession) -> User:
    user = User(email=body.email, hashed_password=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    db.refresh(user)
    return user


@router.post("/login", response_model=UserRead)
def login(body: LoginRequest, db: DbSession, response: Response) -> User:
    user = db.scalar(select(User).where(User.email == body.email))
    password_ok = verify_password(body.password, user.hashed_password if user else DUMMY_HASH)
    if user is None or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    # The client gets the token only in the cookie; the database keeps its hash.
    token = generate_session_token()
    db.add(UserSession(token=hash_session_token(token), user_id=user.id))
    db.commit()
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, secure=True, samesite="lax", path="/"
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    _current_user: CurrentUser,
    request: Request,
    response: Response,
    db: DbSession,
) -> None:
    token = request.cookies[SESSION_COOKIE]
    session = db.scalar(
        select(UserSession).where(UserSession.token == hash_session_token(token))
    )
    db.delete(session)
    db.commit()
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user
