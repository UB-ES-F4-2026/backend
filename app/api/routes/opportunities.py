"""Read investment opportunities."""
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.orm import contains_eager

from app.api.deps import CurrentUser, DbSession
from app.api.routes.promoting_entity import published_projects_count, to_read
from app.core.name_search import search_by_title
from app.models.opportunity import Opportunity, OpportunityStatus, OpportunityType
from app.models.promoting_entity import PromotingEntity
from app.schemas.opportunity import (
    OpportunityCreate,
    OpportunityDetailRead,
    OpportunityRead,
    RealEstateOpportunityRead,
)

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


@router.post("", response_model=OpportunityRead, status_code=status.HTTP_201_CREATED)
def create_opportunity(
    body: OpportunityCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> Opportunity:
    if db.get(PromotingEntity, current_user.id) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debes crear una entidad promotora antes de crear oportunidades",
        )
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
def get_opportunities(
    db: DbSession,
    name: Annotated[str | None, Query(max_length=255)] = None,
) -> list[Opportunity]:
    opportunities = db.scalars(
        select(Opportunity)
        .where(available_opportunity_filter())
        .order_by(Opportunity.created_at.desc())
    ).all()
    # Sin búsqueda (o solo espacios) se devuelve el catálogo completo.
    if name is None or not name.strip():
        return list(opportunities)
    # Solo se busca dentro del catálogo disponible.
    return search_by_title(name, opportunities, lambda opportunity: opportunity.title)


@router.get("/{opportunity_id}", response_model=OpportunityDetailRead)
def get_opportunity(opportunity_id: int, db: DbSession) -> OpportunityDetailRead:
    # Solo es pública una oportunidad inmobiliaria publicada o cerrada con sus
    # datos de inmueble. Los JOIN internos descartan las que no tienen inmueble.
    row = db.execute(
        select(Opportunity, published_projects_count)
        .join(Opportunity.real_estate)
        .join(Opportunity.promoter)
        .options(
            contains_eager(Opportunity.real_estate), contains_eager(Opportunity.promoter)
        )
        .where(
            Opportunity.id == opportunity_id,
            Opportunity.type == OpportunityType.REAL_ESTATE,
            Opportunity.status.in_([OpportunityStatus.PUBLISHED, OpportunityStatus.CLOSED]),
        )
    ).one_or_none()
    if row is None:
        # Misma respuesta para inexistentes, borradores, rechazadas y otros tipos:
        # no se revela cuál de estos casos es.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oportunidad no disponible",
        )
    opportunity, count = row
    return OpportunityDetailRead(
        id=opportunity.id,
        type=opportunity.type,
        status=opportunity.status,
        title=opportunity.title,
        description=opportunity.description,
        location=opportunity.location,
        cover_image_url=opportunity.cover_image_url,
        target_amount_cents=opportunity.target_amount_cents,
        committed_cents=opportunity.committed_cents,
        minimum_contribution_cents=opportunity.minimum_contribution_cents,
        deadline=opportunity.deadline,
        date_published=opportunity.date_published,
        promoter=to_read(opportunity.promoter, count),
        real_estate=RealEstateOpportunityRead.model_validate(opportunity.real_estate),
        server_time=datetime.now(UTC),
    )
