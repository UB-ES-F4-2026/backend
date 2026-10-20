"""Read investment opportunities."""
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import and_, select

from app.api.deps import CurrentUser, DbSession
from app.models.opportunity import Opportunity, OpportunityStatus
from app.schemas.opportunity import OpportunityCreate, OpportunityRead

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


@router.post("", response_model=OpportunityRead, status_code=status.HTTP_201_CREATED)
def create_opportunity(
    body: OpportunityCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> Opportunity:
    opportunity = Opportunity(
        user_id=current_user.id,
        type=body.type,
        title=body.title,
        description=body.description,
        location=body.location,
        cover_image_url=body.cover_image_url,
        target_amount_cents=body.target_amount_cents,
        committed_cents=body.committed_cents,
        deadline=body.deadline,
        date_published=datetime.now(UTC),
    )
    db.add(opportunity)
    db.commit()
    db.refresh(opportunity)
    return opportunity


def available_opportunity_filter():
    return and_(
        Opportunity.status == OpportunityStatus.PUBLISHED,
        Opportunity.deadline > datetime.now(UTC),
        Opportunity.committed_cents < Opportunity.target_amount_cents,
        Opportunity.date_closed.is_(None),
    )


@router.get("", response_model=list[OpportunityRead])
def get_opportunities(db: DbSession):
    opportunities = db.scalars(
        select(Opportunity)
        .where(available_opportunity_filter())
        .order_by(Opportunity.created_at.desc())
    ).all()
    return opportunities


@router.get("/{opportunity_id}", response_model=OpportunityRead)
def get_opportunity(opportunity_id: int, db: DbSession) -> Opportunity:
    opportunity = db.scalar(
        select(Opportunity).where(
            Opportunity.id == opportunity_id
        )
    )
    if opportunity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity not found",
        )
    return opportunity
