"""Login sessions that expire after an hour without requests."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

SESSION_IDLE_TIMEOUT = timedelta(minutes=60)


def new_expiry() -> datetime:
    return datetime.now(UTC) + SESSION_IDLE_TIMEOUT


class UserSession(Base):
    """Store a SHA-256 hash of the token, never the token the client holds."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=new_expiry
    )

    def touch(self) -> None:
        """Call on every authenticated request: expires_at = last request + 60 min."""
        self.expires_at = new_expiry()
