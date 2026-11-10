"""Crear y consultar entidades promotoras."""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.models.opportunity import Opportunity
from app.models.promoting_entity import PromotingEntity
from app.schemas.promoting_entity import PromotingEntityCreate, PromotingEntityRead

router = APIRouter(prefix="/api/promotingentity", tags=["promoting entities"])

# Oportunidades publicadas del usuario, incluidas las cerradas: las que tienen
# fecha de publicación. Excluye borradores y rechazadas nunca publicadas.
published_projects_count = (
    select(func.count(Opportunity.id))
    .where(
        Opportunity.user_id == PromotingEntity.user_id,
        Opportunity.date_published.is_not(None),
    )
    .correlate(PromotingEntity)
    .scalar_subquery()
)


def to_read(entity: PromotingEntity, count: int) -> PromotingEntityRead:
    return PromotingEntityRead(
        user_id=entity.user_id,
        legal_name=entity.legal_name,
        image_url=entity.image_url,
        published_projects_count=count,
        experience_years=entity.experience_years,
        location=entity.location,
    )


@router.post("", response_model=PromotingEntityRead, status_code=status.HTTP_201_CREATED)
def create_promoting_entity(
    body: PromotingEntityCreate, user: CurrentUser, db: DbSession
) -> PromotingEntityRead:
    entity = PromotingEntity(user_id=user.id, **body.model_dump())
    db.add(entity)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "El usuario ya tiene una entidad promotora"
        ) from None
    count = db.scalar(
        select(published_projects_count).where(PromotingEntity.user_id == user.id)
    )
    return to_read(entity, count)


@router.get("", response_model=list[PromotingEntityRead])
def get_promoting_entities(db: DbSession) -> list[PromotingEntityRead]:
    rows = db.execute(
        select(PromotingEntity, published_projects_count).order_by(
            PromotingEntity.created_at
        )
    ).all()
    return [to_read(entity, count) for entity, count in rows]
