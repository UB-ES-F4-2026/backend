"""Creació comuna d'oportunitats pendents de revisió."""
from sqlalchemy.orm import Session

from app.core.commitments import reserve_funds
from app.models.opportunity import Opportunity, OpportunityStatus
from app.schemas.opportunity import OpportunityCreate


def create_pending_opportunity(
    db: Session, *, user_id: int, body: OpportunityCreate
) -> Opportunity:
    """Crea l'oportunitat i la seva reserva inicial dins la transacció rebuda."""
    opportunity = Opportunity(
        user_id=user_id,
        type=body.type,
        status=OpportunityStatus.DRAFT,
        title=body.title,
        description=body.description,
        location=body.location.as_display_location(),
        target_amount_cents=body.target_amount_cents,
        committed_cents=0,
        minimum_contribution_cents=body.minimum_contribution_cents,
        deadline=body.deadline,
        date_published=None,
    )
    db.add(opportunity)
    db.flush()

    if body.initial_contribution_cents is not None:
        reserve_funds(
            db,
            user_id=user_id,
            opportunity_id=opportunity.id,
            amount_cents=body.initial_contribution_cents,
        )

    return opportunity
