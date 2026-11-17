"""Dades específiques de les oportunitats empresarials."""
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum as SqlEnum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.opportunity import Opportunity


class BusinessSector(str, Enum):
    FINTECH = "fintech"
    SAAS = "saas"
    HEALTHTECH = "healthtech"
    BIOTECH = "biotech"
    CLEANTECH = "cleantech"
    AGRITECH = "agritech"
    FOODTECH = "foodtech"
    D2C = "d2c"
    EDTECH = "edtech"
    MEDIA = "media"
    AI = "ai"
    OTHER = "other"


class BusinessPhase(str, Enum):
    PRE_SEED = "pre_seed"
    SEED = "seed"
    EARLY = "early"
    GROWTH = "growth"
    LATE = "late"


class BusinessOpportunity(Base):
    """Registre un a un amb l'oportunitat empresarial pare."""

    __tablename__ = "business_opportunities"
    __table_args__ = (
        CheckConstraint(
            "pre_investment_valuation_cents > 0",
            name="pre_investment_valuation_positive",
        ),
    )

    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True
    )
    sector: Mapped[BusinessSector] = mapped_column(
        SqlEnum(
            BusinessSector,
            name="business_sector",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    phase: Mapped[BusinessPhase] = mapped_column(
        SqlEnum(
            BusinessPhase,
            name="business_phase",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    pre_investment_valuation_cents: Mapped[int] = mapped_column(Integer)

    opportunity: Mapped["Opportunity"] = relationship(back_populates="business")
