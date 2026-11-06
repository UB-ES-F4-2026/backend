"""Request and response bodies for registration and login."""
from datetime import datetime

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    phone: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=8, max_length=72)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, email: str) -> str:
        return email.lower()

    @field_validator("last_name", mode="before")
    @classmethod
    def normalize_last_name(cls, last_name: object) -> object:
        if isinstance(last_name, str):
            return last_name.strip() or None
        return last_name

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, phone: str) -> str:
        try:
            number = phonenumbers.parse(phone, None)
        except NumberParseException as exc:
            raise ValueError("Número de teléfono no válido") from exc

        if not phonenumbers.is_valid_number(number):
            raise ValueError("Número de teléfono no válido")

        return phonenumbers.format_number(number, PhoneNumberFormat.E164)



class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, email: str) -> str:
        return email.lower()



class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    first_name: str | None
    last_name: str | None
    phone: str | None
    created_at: datetime
