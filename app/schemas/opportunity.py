"""Request and response bodies for investment opportunities."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.opportunity import OpportunityStatus, OpportunityType
from app.models.real_estate_opportunity import AssetType, IntendedUse, RealEstatePurpose
from app.schemas.promoting_entity import PromotingEntityRead


class OpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    type: OpportunityType
    title: str
    description: str
    location: str
    cover_image_url: str | None
    target_amount_cents: int
    committed_cents: int
    deadline: datetime
    date_published: datetime | None
    date_closed: datetime | None
    created_at: datetime
    updated_at: datetime

class OpportunityCreate(BaseModel):
    type: OpportunityType
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    location: str = Field(min_length=1, max_length=255)
    cover_image_url: str | None = Field(default=None, max_length=2048)
    target_amount_cents: int = Field(gt=0)
    committed_cents: int = Field(default=0, ge=0)
    deadline: datetime


class RealEstateOpportunityRead(BaseModel):
    """Características del inmueble. Las coordenadas son el punto público aproximado."""

    model_config = ConfigDict(from_attributes=True)

    purpose: RealEstatePurpose
    intended_use: IntendedUse
    asset_type: AssetType
    surface_m2: Decimal
    planned_housing_units: int | None
    estimated_works_end: date | None
    estimated_rental_start: date | None
    public_latitude: Decimal | None
    public_longitude: Decimal | None


class OpportunityDetailRead(BaseModel):
    """Detalle público de una oportunidad inmobiliaria (US02.2.1).

    Solo incluye los datos que muestra el detalle: no expone fechas internas
    ni datos privados del promotor.
    """

    id: int
    type: OpportunityType
    status: OpportunityStatus
    title: str
    description: str
    location: str
    cover_image_url: str | None
    target_amount_cents: int
    committed_cents: int
    minimum_contribution_cents: int | None
    deadline: datetime
    date_published: datetime
    promoter: PromotingEntityRead
    real_estate: RealEstateOpportunityRead
    # Referencia temporal para que el frontend no dependa del reloj local.
    server_time: datetime
