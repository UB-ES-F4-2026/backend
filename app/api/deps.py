"""Dependencies shared by the API routes."""
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.security import SESSION_COOKIE, hash_session_token
from app.database import get_db
from app.models.session import SESSION_IDLE_TIMEOUT, UserSession
from app.models.user import User

DbSession = Annotated[Session, Depends(get_db)]


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

    # Check and renew in one statement: expires_at = this request + 60 min.
    now = datetime.now(UTC)
    user_id = db.scalar(
        update(UserSession)
        .where(
            UserSession.token == hash_session_token(token),
            UserSession.expires_at > now,
        )
        .values(expires_at=now + SESSION_IDLE_TIMEOUT)
        .returning(UserSession.user_id)
    )
    if user_id is None:
        raise unauthorized
    db.commit()

    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
