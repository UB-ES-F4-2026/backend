"""Imatges associades a una oportunitat d'inversió."""
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.opportunity import Opportunity


class OpportunityImage(Base):
    """Fitxer multimèdia ordenat d'una oportunitat.

    La portada és sempre la imatge amb posició zero. La clau emmagatzemada és
    relativa a l'arrel de contingut multimèdia i no exposa cap ruta del sistema.
    """

    __tablename__ = "opportunity_images"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_non_negative"),
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
        UniqueConstraint("opportunity_id", "position", name="opportunity_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    content_type: Mapped[str] = mapped_column(String(32))
    size_bytes: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)

    opportunity: Mapped["Opportunity"] = relationship(back_populates="images")

    @property
    def url(self) -> str:
        """Retorna la ruta HTTP que serveix la imatge sense revelar el disc."""
        return f"/api/opportunities/{self.opportunity_id}/images/{self.id}"
