"""Entidad promotora asociada a un usuario: su perfil público como promotor."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PromotingEntity(Base):
    """Cada usuario puede tener como máximo una entidad promotora.

    El número de proyectos publicados no se guarda: se calcula a partir de las
    oportunidades del usuario.
    """

    __tablename__ = "promoting_entities"
    __table_args__ = (
        CheckConstraint("experience_years >= 0", name="experience_years_non_negative"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    legal_name: Mapped[str] = mapped_column(String(255))
    image_url: Mapped[str | None] = mapped_column(String(2048))
    experience_years: Mapped[int | None]
    location: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
