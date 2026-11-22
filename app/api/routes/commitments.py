"""Comprometre saldo en una oportunitat en finançament."""
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, DbSession
from app.core.commitments import (
    BelowMinimumContribution,
    CommitmentError,
    InsufficientFunds,
    OpportunityNotFound,
    ensure_in_funding,
    ensure_minimum_contribution,
    lock_opportunity,
    reserve_funds,
)
from app.core.wallet import lock_wallet
from app.models.opportunity import Opportunity, OpportunityStatus, OpportunityType
from app.schemas.commitment import (
    CommitmentCreate,
    CommitmentRead,
    CommitmentResultRead,
    OpportunityFundingRead,
)
from app.schemas.wallet import BalanceRead

router = APIRouter(prefix="/api/opportunities", tags=["commitments"])

NOT_AVAILABLE = "Opportunity not available"
BELOW_MINIMUM = "Amount below the minimum contribution"
INSUFFICIENT_FUNDS = "Insufficient funds"
NOT_ACCEPTED = "Opportunity no longer accepts this contribution"


def is_public_real_estate(opportunity: Opportunity) -> bool:
    # El mateix criteri que el detall públic: esborranys, rebutjades i altres
    # tipus no existeixen per a l'usuari.
    return opportunity.type == OpportunityType.REAL_ESTATE and opportunity.status in (
        OpportunityStatus.PUBLISHED,
        OpportunityStatus.CLOSED,
    )


def to_http_error(error: CommitmentError) -> HTTPException:
    if isinstance(error, OpportunityNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, NOT_AVAILABLE)
    if isinstance(error, BelowMinimumContribution):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, BELOW_MINIMUM)
    if isinstance(error, InsufficientFunds):
        return HTTPException(status.HTTP_409_CONFLICT, INSUFFICIENT_FUNDS)
    # Ja no està en finançament o no li queda prou capital pendent.
    return HTTPException(status.HTTP_409_CONFLICT, NOT_ACCEPTED)


@router.post(
    "/{opportunity_id}/commitments",
    response_model=CommitmentResultRead,
    status_code=status.HTTP_201_CREATED,
)
def commit_contribution(
    opportunity_id: int,
    body: CommitmentCreate,
    current_user: CurrentUser,
    db: DbSession,
    response: Response,
) -> CommitmentResultRead:
    """Compromet una aportació de l'usuari autenticat en una oportunitat immobiliària.

    Totes les comprovacions es fan amb l'oportunitat i el wallet bloquejats, de
    manera que el saldo i la disponibilitat es revaliden en el moment de confirmar.
    """
    response.headers["Cache-Control"] = "no-store"
    try:
        opportunity = lock_opportunity(db, opportunity_id)
        if not is_public_real_estate(opportunity):
            raise OpportunityNotFound(opportunity_id)
        ensure_in_funding(opportunity, datetime.now(UTC))
        ensure_minimum_contribution(opportunity, body.amount_cents)
        commitment = reserve_funds(
            db,
            user_id=current_user.id,
            opportunity_id=opportunity_id,
            amount_cents=body.amount_cents,
        )
    except CommitmentError as error:
        # No s'ha modificat res; el rollback allibera els bloquejos.
        db.rollback()
        raise to_http_error(error) from None

    wallet = lock_wallet(db, current_user.id)
    result = CommitmentResultRead(
        commitment=CommitmentRead.model_validate(commitment),
        opportunity=OpportunityFundingRead.model_validate(opportunity),
        wallet=BalanceRead(
            available_cents=wallet.available_cents,
            committed_cents=wallet.committed_cents,
        ),
    )
    db.commit()
    return result
