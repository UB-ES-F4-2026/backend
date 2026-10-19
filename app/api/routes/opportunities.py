"""Read investment opportunities."""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.opportunity import Opportunity
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
    )
    db.add(opportunity)
    db.commit()
    db.refresh(opportunity)
    return opportunity


@router.get("", response_model=list[OpportunityRead])
def list_opportunities(
    db: DbSession,
    skip: int = 0,
    limit: int = 100,
) -> list[Opportunity]:
    opportunities = db.scalars(
        select(Opportunity)
        .order_by(Opportunity.created_at.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return list(opportunities)


@router.get("/{opportunity_id}", response_model=OpportunityRead)
def get_opportunity(opportunity_id: int, db: DbSession) -> Opportunity:
    opportunity = db.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity not found",
        )
    return opportunity
