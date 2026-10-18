"""Register, log in and fetch the logged-in user."""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.core.security import DUMMY_HASH, create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, Token, UserRead

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


@router.post("/login", response_model=Token)
def login(body: LoginRequest, db: DbSession) -> Token:
    user = db.scalar(select(User).where(User.email == body.email))
    password_ok = verify_password(body.password, user.hashed_password if user else DUMMY_HASH)
    if user is None or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user
