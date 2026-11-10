from pydantic import BaseModel, Field
from typing import Literal

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
