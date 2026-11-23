"""Comprometre saldo en una oportunitat en finançament."""
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, DbSession
from app.core.commitments import (
    BelowMinimumContribution,
    CommitmentError,
    InsufficientFunds,
    OpportunityNotFound,
    ensure_in_funding,
    ensure_minimum_contribution,
    estimated_equity_percent,
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


def is_public(opportunity: Opportunity) -> bool:
    # El mateix criteri que el detall públic: no existeixen per a l'usuari els
    # esborranys, les rebutjades ni les que no tenen les dades del seu tipus.
    if opportunity.status not in (OpportunityStatus.PUBLISHED, OpportunityStatus.CLOSED):
        return False
    if opportunity.type == OpportunityType.REAL_ESTATE:
        return opportunity.real_estate is not None
    return opportunity.business is not None


def estimated_equity(opportunity: Opportunity, amount_cents: int) -> Decimal | None:
    """Participació estimada de la inversió; les aportacions immobiliàries no en tenen."""
    if opportunity.type != OpportunityType.EQUITY:
        return None
    return estimated_equity_percent(
        amount_cents,
        pre_investment_valuation_cents=opportunity.business.pre_investment_valuation_cents,
        target_amount_cents=opportunity.target_amount_cents,
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
    """Compromet una aportació o una inversió de l'usuari autenticat en una oportunitat.

    Serveix per a les oportunitats immobiliàries i les empresarials; en aquestes
    últimes la resposta inclou la participació estimada.

    Totes les comprovacions es fan amb l'oportunitat i el wallet bloquejats, de
    manera que el saldo i la disponibilitat es revaliden en el moment de confirmar.
    """
    response.headers["Cache-Control"] = "no-store"
    try:
        opportunity = lock_opportunity(db, opportunity_id)
        if not is_public(opportunity):
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
        commitment=CommitmentRead(
            id=commitment.id,
            opportunity_id=commitment.opportunity_id,
            amount_cents=commitment.amount_cents,
            created_at=commitment.created_at,
            estimated_equity=estimated_equity(opportunity, commitment.amount_cents),
        ),
        opportunity=OpportunityFundingRead.model_validate(opportunity),
        wallet=BalanceRead(
            available_cents=wallet.available_cents,
            committed_cents=wallet.committed_cents,
        ),
    )
    db.commit()
    return result
