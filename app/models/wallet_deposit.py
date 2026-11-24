"""Pagaments de Stripe acreditats a un wallet."""
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WalletDeposit(Base):
    """Persisteix l'esdeveniment perquè un reintent no acrediti dues vegades."""

    __tablename__ = "wallet_deposits"
    __table_args__ = (
        CheckConstraint("amount_cents >= 50", name="amount_at_least_minimum"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stripe_event_id: Mapped[str] = mapped_column(String(255), unique=True)
    stripe_payment_intent_id: Mapped[str] = mapped_column(String(255), unique=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="eur", server_default="eur")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
