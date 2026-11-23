"""Cossos de petició i resposta dels compromisos."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.funding import FundingStatus
from app.models.opportunity import OpportunityType
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
    # Percentatge de l'empresa; només en oportunitats empresarials.
    estimated_equity: Decimal | None = None


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


class CommitmentOpportunityRead(BaseModel):
    """Estat actual de l'oportunitat d'un compromís, tal com es mostra a «Mis inversiones»."""

    id: int
    title: str
    type: OpportunityType
    # Estat en el moment de la consulta, no el que tenia en comprometre l'import.
    funding_status: FundingStatus
    target_amount_cents: int
    committed_cents: int
    deadline: datetime
    # Només les oportunitats públiques tenen detall: una aportació inicial a una
    # oportunitat pròpia pendent de revisió es llista, però no s'hi pot enllaçar.
    is_public: bool


class UserCommitmentRead(BaseModel):
    """Un compromís de l'usuari autenticat amb l'oportunitat on ha invertit."""

    id: int
    amount_cents: int
    created_at: datetime
    # Percentatge de l'empresa; només en oportunitats empresarials.
    estimated_equity: Decimal | None
    opportunity: CommitmentOpportunityRead


class UserCommitmentsSummaryRead(BaseModel):
    # Suma de tots els compromisos de la llista: coincideix amb el saldo compromès.
    total_committed_cents: int
    commitments_count: int
    # Compromisos, no oportunitats: dos en la mateixa oportunitat compten dos.
    in_funding_count: int


class UserCommitmentsRead(BaseModel):
    """Resum i llista dels compromisos de l'usuari, del més recent al més antic."""

    summary: UserCommitmentsSummaryRead
    commitments: list[UserCommitmentRead]
