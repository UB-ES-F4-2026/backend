"""Cuerpos de petición y respuesta de las entidades promotoras."""
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PromotingEntityRegistration(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    legal_name: str = Field(min_length=1, max_length=255)
    founding_year: int | None = Field(default=None, ge=1000, le=9999)
    location: str | None = Field(default=None, max_length=255)

    @field_validator("founding_year")
    @classmethod
    def validate_founding_year(cls, year: int | None) -> int | None:
        if year is not None and year > datetime.now(UTC).year:
            raise ValueError("L'any de fundació no pot ser posterior a l'any actual")
        return year


class PromotingEntityCreate(PromotingEntityRegistration):
    image_url: str | None = Field(default=None, max_length=2048)
    experience_years: int | None = Field(default=None, ge=0)


class PromotingEntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    legal_name: str
    image_url: str | None
    published_projects_count: int
    experience_years: int | None
    founding_year: int | None
    location: str | None
