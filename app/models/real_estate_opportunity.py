"""Datos específicos de las oportunidades inmobiliarias."""
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, Enum as SqlEnum, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.opportunity import Opportunity


class RealEstatePurpose(str, Enum):
    ACQUISITION = "acquisition"
    CONSTRUCTION = "construction"
    RENOVATION = "renovation"
    ACQUISITION_AND_RENOVATION = "acquisition_and_renovation"


class IntendedUse(str, Enum):
    RENTAL = "rental"
    SALE = "sale"
    OWN_USE = "own_use"


class AssetType(str, Enum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    LAND = "land"
    MIXED = "mixed"


class RealEstateOpportunity(Base):
    """Registro uno a uno con su oportunidad padre, con la que comparte el id.

    Los datos comunes (tipo, promotor, estado, importes, fechas...) solo se
    guardan en `opportunities`.
    """

    __tablename__ = "real_estate_opportunities"
    __table_args__ = (
        CheckConstraint("surface_m2 > 0", name="surface_positive"),
        CheckConstraint("planned_housing_units > 0", name="planned_housing_units_positive"),
        # Viviendas previstas: obligatorias para residential y mixed, nulas para el resto.
        CheckConstraint(
            "(asset_type IN ('residential', 'mixed')) = (planned_housing_units IS NOT NULL)",
            name="housing_units_match_asset_type",
        ),
        CheckConstraint("public_latitude BETWEEN -90 AND 90", name="public_latitude_range"),
        CheckConstraint("public_longitude BETWEEN -180 AND 180", name="public_longitude_range"),
        # Las coordenadas se informan juntas o ninguna.
        CheckConstraint(
            "(public_latitude IS NULL) = (public_longitude IS NULL)",
            name="public_coordinates_together",
        ),
        # Solo hay obras si la finalidad incluye construcción o rehabilitación.
        CheckConstraint(
            "estimated_works_end IS NULL OR purpose <> 'acquisition'",
            name="works_end_requires_works",
        ),
        CheckConstraint(
            "estimated_rental_start IS NULL OR intended_use = 'rental'",
            name="rental_start_requires_rental",
        ),
    )

    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True
    )
    purpose: Mapped[RealEstatePurpose] = mapped_column(
        SqlEnum(
            RealEstatePurpose,
            name="real_estate_purpose",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    intended_use: Mapped[IntendedUse] = mapped_column(
        SqlEnum(
            IntendedUse,
            name="real_estate_intended_use",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    asset_type: Mapped[AssetType] = mapped_column(
        SqlEnum(
            AssetType,
            name="real_estate_asset_type",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    surface_m2: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    planned_housing_units: Mapped[int | None]
    estimated_works_end: Mapped[date | None] = mapped_column(Date)
    estimated_rental_start: Mapped[date | None] = mapped_column(Date)
    public_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    public_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    opportunity: Mapped["Opportunity"] = relationship(back_populates="real_estate")
