"""Cuerpos de petición y respuesta de las entidades promotoras."""
from pydantic import BaseModel, ConfigDict, Field


class PromotingEntityCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    legal_name: str = Field(min_length=1, max_length=255)
    image_url: str | None = Field(default=None, max_length=2048)
    experience_years: int | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=255)


class PromotingEntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    legal_name: str
    image_url: str | None
    published_projects_count: int
    experience_years: int | None
    location: str | None
