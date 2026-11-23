"""Compromisos: imports que un usuari reserva del seu saldo per a una oportunitat."""
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Commitment(Base):
    """Un compromís reserva saldo; no és un cobrament ni una compra de participacions.

    Un usuari pot tenir diversos compromisos sobre la mateixa oportunitat: cada
    aportació es registra per separat. Són registres financers, de manera que
    no s'esborren en cascada amb l'usuari ni amb l'oportunitat.
    """

    __tablename__ = "commitments"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="amount_cents_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="RESTRICT"), index=True
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
