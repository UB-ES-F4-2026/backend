"""Request and response bodies for investment opportunities."""
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.models.opportunity import OpportunityStatus, OpportunityType
from app.models.business_opportunity import BusinessPhase, BusinessSector
from app.models.real_estate_opportunity import AssetType, IntendedUse, RealEstatePurpose
from app.schemas.promoting_entity import PromotingEntityRead


class OpportunityImageRead(BaseModel):
    """Referència pública a una imatge ordenada d'una oportunitat."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    content_type: str
    position: int
    url: str


class OpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    type: OpportunityType
    title: str
    description: str
    location: str
    cover_image_url: str | None
    images: list[OpportunityImageRead] = Field(default_factory=list)
    target_amount_cents: int
    committed_cents: int
    deadline: datetime
    date_published: datetime | None
    date_closed: datetime | None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def set_cover_image_from_gallery(self) -> "OpportunityRead":
        if self.images:
            self.cover_image_url = self.images[0].url
        return self

class OpportunityLocationCreate(BaseModel):
    municipality: str = Field(min_length=1, max_length=100)
    province: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=1, max_length=100)

    @field_validator("municipality", "province", "country")
    @classmethod
    def normalize_component(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Location component is required")
        return normalized

    def as_display_location(self) -> str:
        return f"{self.municipality}, {self.province}, {self.country}"


class RealEstateOpportunityCreate(BaseModel):
    """Dades específiques per crear una oportunitat immobiliària."""

    purpose: RealEstatePurpose
    intended_use: IntendedUse
    asset_type: AssetType
    surface_m2: Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]
    planned_housing_units: Annotated[StrictInt, Field(gt=0)] | None = None
    estimated_works_end: date | None = None
    estimated_rental_start: date | None = None
    public_latitude: Annotated[Decimal, Field(ge=-90, le=90)] | None = None
    public_longitude: Annotated[Decimal, Field(ge=-180, le=180)] | None = None

    @model_validator(mode="after")
    def validate_conditional_fields(self) -> "RealEstateOpportunityCreate":
        requires_housing_units = self.asset_type in {
            AssetType.RESIDENTIAL,
            AssetType.MIXED,
        }
        if requires_housing_units != (self.planned_housing_units is not None):
            raise ValueError(
                "Planned housing units must match the selected asset type"
            )
        if (
            self.estimated_works_end is not None
            and self.purpose == RealEstatePurpose.ACQUISITION
        ):
            raise ValueError("Estimated works end requires works")
        if (
            self.estimated_rental_start is not None
            and self.intended_use != IntendedUse.RENTAL
        ):
            raise ValueError("Estimated rental start requires rental use")
        if (self.public_latitude is None) != (self.public_longitude is None):
            raise ValueError("Public coordinates must be provided together")
        return self


class OpportunityCreate(BaseModel):
    type: OpportunityType
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    location: OpportunityLocationCreate
    target_amount_cents: Annotated[StrictInt, Field(gt=0)]
    minimum_contribution_cents: Annotated[StrictInt, Field(gt=0)]
    deadline: datetime
    initial_contribution_cents: Annotated[StrictInt, Field(gt=0)] | None = None
    real_estate: RealEstateOpportunityCreate | None = None

    @field_validator("title", "description")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value is required")
        return normalized

    @field_validator("deadline")
    @classmethod
    def validate_future_deadline(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value <= datetime.now(UTC):
            raise ValueError("Deadline must be in the future")
        return value

    @model_validator(mode="after")
    def validate_initial_contribution(self) -> "OpportunityCreate":
        if self.minimum_contribution_cents > self.target_amount_cents:
            raise ValueError("Minimum contribution cannot exceed target amount")
        if self.initial_contribution_cents is not None and not (
            self.minimum_contribution_cents
            <= self.initial_contribution_cents
            <= self.target_amount_cents
        ):
            raise ValueError("Initial contribution must be within the funding range")
        return self

    @model_validator(mode="after")
    def validate_type_specific_data(self) -> "OpportunityCreate":
        if self.type == OpportunityType.REAL_ESTATE and self.real_estate is None:
            raise ValueError("Real estate data is required")
        if self.type != OpportunityType.REAL_ESTATE and self.real_estate is not None:
            raise ValueError("Real estate data requires a real estate opportunity")
        return self


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


class RealEstateOpportunityDetailRead(BaseModel):
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
    images: list[OpportunityImageRead] = Field(default_factory=list)
    target_amount_cents: int
    committed_cents: int
    minimum_contribution_cents: int | None
    deadline: datetime
    date_published: datetime
    promoter: PromotingEntityRead
    real_estate: RealEstateOpportunityRead
    # Referencia temporal para que el frontend no dependa del reloj local.
    server_time: datetime

    @model_validator(mode="after")
    def set_cover_image_from_gallery(self) -> "RealEstateOpportunityDetailRead":
        if self.images:
            self.cover_image_url = self.images[0].url
        return self

class BusinessOpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sector: BusinessSector
    phase: BusinessPhase
    pre_investment_valuation_cents: int
    equity_offered: Decimal


class BusinessOpportunityDetailRead(BaseModel):
    """Detall d'una oportunitat empresarial accessible sense sessió requerida."""

    id: int
    type: OpportunityType
    status: OpportunityStatus
    title: str
    description: str
    location: str
    cover_image_url: str | None
    images: list[OpportunityImageRead] = Field(default_factory=list)
    target_amount_cents: int
    committed_cents: int
    minimum_contribution_cents: int | None
    date_published: datetime
    deadline: datetime
    promoter: PromotingEntityRead
    business: BusinessOpportunityRead
    server_time: datetime

    @model_validator(mode="after")
    def set_cover_image_from_gallery(self) -> "BusinessOpportunityDetailRead":
        if self.images:
            self.cover_image_url = self.images[0].url
        return self
