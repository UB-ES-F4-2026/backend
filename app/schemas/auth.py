"""Request and response bodies for registration and login."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, email: str) -> str:
        return email.lower()

    @field_validator("password")
    @classmethod
    def fits_bcrypt(cls, password: str) -> str:
        # bcrypt only accepts up to 72 bytes.
        if len(password.encode()) > 72:
            raise ValueError("Password must be at most 72 bytes")
        return password


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, email: str) -> str:
        return email.lower()

    @field_validator("password")
    @classmethod
    def fits_bcrypt(cls, password: str) -> str:
        # bcrypt only accepts up to 72 bytes.
        if len(password.encode()) > 72:
            raise ValueError("Password must be at most 72 bytes")
        return password


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
