"""Dades específiques de les oportunitats empresarials."""
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum as SqlEnum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.opportunity import Opportunity


class BusinessSector(str, Enum):
    TECHNOLOGY = "technology"
    INDUSTRY = "industry"
    FOOD_AND_BEVERAGE = "food_and_beverage"
    COMMERCE = "commerce"
    HEALTH = "health"
    ENERGY = "energy"
    TOURISM_AND_LEISURE = "tourism_and_leisure"
    OTHER_SERVICES = "other_services"


class BusinessPhase(str, Enum):
    IDEA = "idea"
    LAUNCH = "launch"
    GROWTH = "growth"
    CONSOLIDATED = "consolidated"


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
