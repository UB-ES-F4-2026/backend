"""Investment opportunities offered by the platform."""
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.promoting_entity import PromotingEntity
from app.models.real_estate_opportunity import RealEstateOpportunity


class OpportunityType(str, Enum):
    REAL_ESTATE = "real_estate"
    EQUITY = "equity"


class OpportunityStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    REJECTED = "rejected"
    CLOSED = "closed"


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        # El porcentaje de financiación divide por el objetivo: no puede ser cero.
        CheckConstraint("target_amount_cents > 0", name="target_amount_positive"),
        CheckConstraint("committed_cents >= 0", name="committed_amount_non_negative"),
        CheckConstraint(
            "minimum_contribution_cents > 0", name="minimum_contribution_positive"
        ),
        # Solo published y closed son públicas, y requieren fecha de publicación.
        CheckConstraint(
            "status NOT IN ('published', 'closed') OR date_published IS NOT NULL",
            name="public_status_requires_date_published",
        ),
        # closed es un cierre anticipado: date_closed guarda cuándo se produjo.
        CheckConstraint(
            "(status = 'closed') = (date_closed IS NOT NULL)",
            name="closed_status_matches_date_closed",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Toda oportunidad pertenece a una entidad promotora (su clave es el id del usuario).
    user_id: Mapped[int] = mapped_column(
        ForeignKey("promoting_entities.user_id", ondelete="CASCADE"), index=True
    )
    type: Mapped[OpportunityType] = mapped_column(
        SqlEnum(
            OpportunityType,
            name="opportunity_type",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    status: Mapped[OpportunityStatus] = mapped_column(
        SqlEnum(
            OpportunityStatus,
            name="opportunity_status",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=OpportunityStatus.PUBLISHED,  # Canviar quan afegim el rol de verificador
        server_default=OpportunityStatus.PUBLISHED.value,
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(255))
    cover_image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    target_amount_cents: Mapped[int] = mapped_column(Integer)
    committed_cents: Mapped[int] = mapped_column(Integer, default=0)
    # Nulable: los registros existentes no la tienen y no se inventan valores.
    minimum_contribution_cents: Mapped[int | None] = mapped_column(Integer)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    date_published: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    date_closed: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    promoter: Mapped[PromotingEntity] = relationship()
    # Datos específicos de la categoría inmobiliaria, si los tiene.
    real_estate: Mapped[RealEstateOpportunity | None] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan", passive_deletes=True
    )
