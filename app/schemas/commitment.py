"""Cossos de petició i resposta dels compromisos."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.wallet import MAX_SAFE_CENTS, BalanceRead


class CommitmentCreate(BaseModel):
    # Estricte: l'import arriba en cèntims enters, no com a text ni amb decimals.
    amount_cents: int = Field(gt=0, le=MAX_SAFE_CENTS, strict=True)


class CommitmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    opportunity_id: int
    amount_cents: int
    created_at: datetime


class OpportunityFundingRead(BaseModel):
    """Capital de l'oportunitat després del compromís, per actualitzar-ne el progrés."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    target_amount_cents: int
    committed_cents: int


class CommitmentResultRead(BaseModel):
    """Compromís creat, amb el capital de l'oportunitat i el saldo ja actualitzats."""

    commitment: CommitmentRead
    opportunity: OpportunityFundingRead
    wallet: BalanceRead
