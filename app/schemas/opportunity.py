"""Request and response bodies for investment opportunities."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.opportunity import OpportunityType


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


class OpportunityList(BaseModel):
    items: list[OpportunityRead]
    message: str | None = None


class OpportunityCreate(BaseModel):
    type: OpportunityType
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    location: str = Field(min_length=1, max_length=255)
    cover_image_url: str | None = Field(default=None, max_length=2048)
    target_amount_cents: int = Field(gt=0)
    committed_cents: int = Field(default=0, ge=0)
    deadline: datetime
