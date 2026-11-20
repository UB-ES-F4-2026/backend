"""Entidad promotora asociada a un usuario: su perfil público como promotor."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class PromotingEntity(Base):
    """Cada usuario puede tener como máximo una entidad promotora.

    El número de proyectos publicados no se guarda: se calcula a partir de las
    oportunidades del usuario.
    """

    __tablename__ = "promoting_entities"
    __table_args__ = (
        CheckConstraint("experience_years >= 0", name="experience_years_non_negative"),
        CheckConstraint(
            "founding_year >= 1000 AND founding_year <= 9999",
            name="founding_year_four_digits",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    legal_name: Mapped[str] = mapped_column(String(255))
    image_url: Mapped[str | None] = mapped_column(String(2048))
    experience_years: Mapped[int | None]
    founding_year: Mapped[int | None]
    location: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    user: Mapped["User"] = relationship(back_populates="promoting_entity")
