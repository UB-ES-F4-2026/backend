from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt, field_validator

MAX_SAFE_CENTS = 2**53 - 1

IBAN_LENGTHS = {
    "AD": 24, "AE": 23, "AL": 28, "AT": 20, "AZ": 28, "BA": 20,
    "BE": 16, "BG": 22, "BH": 22, "BI": 16, "BJ": 28, "BR": 29,
    "BF": 27, "BY": 28, "CF": 27, "CG": 27, "CH": 21, "CI": 28,
    "CM": 27, "CR": 22, "CV": 25, "CY": 28, "CZ": 24, "DE": 22,
    "DJ": 27, "DK": 18, "DO": 28, "DZ": 24, "EE": 20, "EG": 29,
    "ES": 24, "FI": 18, "FO": 18, "FR": 27, "GA": 27, "GB": 22,
    "GE": 22, "GI": 23, "GL": 18, "GQ": 27, "GR": 27, "GT": 28,
    "GW": 25, "HN": 28, "HR": 21, "HU": 28, "IE": 22, "IL": 23,
    "IQ": 23, "IS": 26, "IT": 27, "JO": 30, "KW": 30, "KZ": 20,
    "LB": 28, "LC": 32, "LI": 21, "LT": 20, "LU": 20, "LV": 21,
    "LY": 25, "MA": 28, "MC": 27, "MD": 24, "ME": 22, "MG": 27,
    "MK": 19, "ML": 28, "MR": 27, "MT": 31, "MU": 30, "MZ": 25,
    "NE": 28, "NI": 28, "NL": 18, "NO": 15, "OM": 23, "PK": 24,
    "PL": 28, "PS": 29, "PT": 25, "QA": 29, "RO": 24, "RS": 22,
    "SA": 24, "SC": 31, "SD": 18, "SE": 24, "SI": 19, "SK": 24,
    "SM": 27, "SN": 28, "ST": 25, "SV": 28, "TD": 27, "TG": 28,
    "TL": 23, "TN": 24, "TR": 26, "UA": 29, "VA": 22, "VG": 24,
    "XK": 20,
}

class BalanceRead(BaseModel):
    available_cents: int = Field(
        ge=0,
        le=MAX_SAFE_CENTS,
        description=(
            "Saldo en céntimos de euro; máximo representable sin pérdida en "
            f"JavaScript: {MAX_SAFE_CENTS}."
        ),
    )
    committed_cents: int = Field(
        ge=0,
        le=MAX_SAFE_CENTS,
        description=(
            "Saldo reservat en compromisos, en cèntims d'euro. No forma part "
            "del saldo disponible ni es pot retirar."
        ),
    )
    currency: Literal["eur"] = "eur"


class DepositIntentCreate(BaseModel):
    amount_cents: Annotated[StrictInt, Field(ge=50, le=MAX_SAFE_CENTS)]


class DepositIntentResponse(BaseModel):
    client_secret: str
    payment_intent_id: str


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
        expected_length = IBAN_LENGTHS.get(normalized[:2])
        if expected_length is None or len(normalized) != expected_length:
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
