"""Dependencies shared by the API routes."""
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import SESSION_COOKIE, hash_session_token
from app.database import get_db
from app.models.session import SESSION_IDLE_TIMEOUT, UserSession
from app.models.user import User

DbSession = Annotated[Session, Depends(get_db)]


def expired_session_exception() -> HTTPException:
    cookie_response = Response()
    cookie_response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing session",
        headers={"Set-Cookie": cookie_response.headers["set-cookie"]},
    )


def get_current_user(request: Request, db: DbSession) -> User:
    """Protect a route: validate the session cookie and renew its expiry.

    Acts as the authentication middleware for every route that depends on it;
    public routes (login, register, health, docs) simply do not.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing session",
    )
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise unauthorized

    now = datetime.now(UTC)
    session = db.scalar(
        select(UserSession).where(UserSession.token == hash_session_token(token))
    )
    if session is None:
        raise unauthorized

    if session.expires_at <= now:
        db.delete(session)
        db.commit()
        raise expired_session_exception()

    session.touch()
    db.commit()

    user = db.get(User, session.user_id)
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
