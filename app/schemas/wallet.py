"""Schemas for wallet operations and payment gateway integration."""
from pydantic import BaseModel, Field
from typing import Literal


class BalanceRead(BaseModel):
    available_cents: int
    currency: Literal["eur"] = "eur"


class DepositIntentCreate(BaseModel):
    amount_cents: int = Field(
        ...,
        ge=50,
        description="Monto a ingresar en céntimos de euro (ej. 5000 para 50,00 €)"
    )


class DepositIntentResponse(BaseModel):
    client_secret: str = Field(..., description="Secreto del cliente para confirmar el pago en frontend")
    payment_intent_id: str = Field(..., description="Identificador único del PaymentIntent en Stripe")


class WalletBalanceResponse(BaseModel):
    available_cents: int
    currency: Literal["eur"] = "eur"