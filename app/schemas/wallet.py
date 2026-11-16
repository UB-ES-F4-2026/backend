from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt, field_validator

MAX_SAFE_CENTS = 2**53 - 1

class BalanceRead(BaseModel):
    available_cents: int = Field(
        ge=0,
        le=MAX_SAFE_CENTS,
        description=(
            "Saldo en céntimos de euro; máximo representable sin pérdida en "
            f"JavaScript: {MAX_SAFE_CENTS}."
        ),
    )
    currency: Literal["eur"] = "eur"


class WithdrawalRequest(BaseModel):
    amount_cents: Annotated[StrictInt, Field(ge=50, le=MAX_SAFE_CENTS)]
    iban: Annotated[str, Field(min_length=15, max_length=34)]
    account_holder: Annotated[str, Field(min_length=1, max_length=140)]

    @field_validator("iban")
    @classmethod
    def normalize_and_validate_iban(cls, value: str) -> str:
        normalized = "".join(value.split()).upper()
        if not normalized.isalnum() or not 15 <= len(normalized) <= 34:
            raise ValueError("Invalid IBAN")
        if not normalized[:2].isalpha() or not normalized[2:4].isdigit():
            raise ValueError("Invalid IBAN")

        rearranged = normalized[4:] + normalized[:4]
        remainder = 0
        for character in rearranged:
            digits = str(ord(character) - 55) if character.isalpha() else character
            for digit in digits:
                remainder = (remainder * 10 + int(digit)) % 97
        if remainder != 1:
            raise ValueError("Invalid IBAN")
        return normalized

    @field_validator("account_holder")
    @classmethod
    def normalize_account_holder(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Account holder is required")
        return normalized


class WithdrawalRead(BaseModel):
    amount_cents: int = Field(ge=50, le=MAX_SAFE_CENTS)
    masked_iban: str
    account_holder: str
    available_cents: int = Field(ge=0, le=MAX_SAFE_CENTS)
    currency: Literal["eur"] = "eur"
