"""Password hashing and session tokens."""
import hashlib
import secrets

import bcrypt

SESSION_COOKIE = "session"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed_password.encode())


# Compared against when the email does not exist, so both cases take as long.
DUMMY_HASH = hash_password("dummy-password")


def generate_session_token() -> str:
    """Random, unguessable token given to the client (256 bits)."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """What the sessions table stores, so a database leak exposes no usable tokens."""
    return hashlib.sha256(token.encode()).hexdigest()
