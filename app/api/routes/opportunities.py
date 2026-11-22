"""Read investment opportunities."""
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import and_, select
from sqlalchemy.orm import contains_eager

from app.api.deps import CurrentUser, DbSession, OptionalCurrentUser
from app.api.routes.promoting_entity import published_projects_count, to_read
from app.core.commitments import CommitmentError, InsufficientFunds
from app.core import media
from app.core.media import (
    InvalidImage,
    delete_staged_images,
    delete_stored_images,
    stage_images,
)
from app.core.name_search import search_by_title
from app.core.opportunity_creation import create_pending_opportunity
from app.models.opportunity import Opportunity, OpportunityStatus, OpportunityType
from app.models.opportunity_image import OpportunityImage
from app.models.promoting_entity import PromotingEntity
from app.schemas.opportunity import (
    BusinessOpportunityDetailRead,
    BusinessOpportunityRead,
    OpportunityCreate,
    RealEstateOpportunityDetailRead,
    OpportunityRead,
    RealEstateOpportunityRead,
)

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


@router.post("", response_model=OpportunityRead, status_code=status.HTTP_201_CREATED)
async def create_opportunity(
    current_user: CurrentUser,
    db: DbSession,
    metadata: str = Form(),
    images: list[UploadFile] = File(),
) -> Opportunity:
    try:
        body = OpportunityCreate.model_validate_json(metadata)
    except ValidationError as exception:
        raise RequestValidationError(exception.errors()) from exception

    if db.get(PromotingEntity, current_user.id) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A promoting entity is required to create opportunities",
        )
    staged_images = []
    stored_images = []
    try:
        staged_images = await stage_images(images)
        opportunity, stored_images = create_pending_opportunity(
            db,
            user_id=current_user.id,
            body=body,
            staged_images=staged_images,
        )
        db.commit()
    except InvalidImage as exception:
        db.rollback()
        delete_staged_images(staged_images)
        delete_stored_images(stored_images)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exception),
        ) from None
    except InsufficientFunds:
        db.rollback()
        delete_staged_images(staged_images)
        delete_stored_images(stored_images)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Insufficient available balance",
        ) from None
    except CommitmentError:
        db.rollback()
        delete_staged_images(staged_images)
        delete_stored_images(stored_images)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Initial contribution could not be reserved",
        ) from None
    except Exception:
        db.rollback()
        delete_staged_images(staged_images)
        delete_stored_images(stored_images)
        raise
    db.refresh(opportunity)
    return opportunity


@router.get("/{opportunity_id}/images/{image_id}")
def get_opportunity_image(
    opportunity_id: int,
    image_id: int,
    current_user: OptionalCurrentUser,
    db: DbSession,
) -> FileResponse:
    image = db.scalar(
        select(OpportunityImage).where(
            OpportunityImage.id == image_id,
            OpportunityImage.opportunity_id == opportunity_id,
        )
    )
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    opportunity = db.get(Opportunity, image.opportunity_id)
    is_public = opportunity.status in {
        OpportunityStatus.PUBLISHED,
        OpportunityStatus.CLOSED,
    }
    is_owner = current_user is not None and current_user.id == opportunity.user_id
    if not is_public and not is_owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    image_path = media.MEDIA_ROOT / image.storage_key
    if not image_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return FileResponse(image_path, media_type=image.content_type)


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
    opportunity_type: Annotated[
        OpportunityType | None, Query(alias="type")
    ] = None,
) -> list[Opportunity]:
    filters = [available_opportunity_filter()]
    if opportunity_type is not None:
        filters.append(Opportunity.type == opportunity_type)

    opportunities = db.scalars(
        select(Opportunity)
        .where(*filters)
        .order_by(Opportunity.created_at.desc())
    ).all()

    if name is None or not name.strip():
        return list(opportunities)

    return search_by_title(
        query=name,
        items=opportunities,
        title=lambda opportunity: opportunity.title,
    )


@router.get(
    "/{opportunity_id}",
    response_model=RealEstateOpportunityDetailRead | BusinessOpportunityDetailRead,
)
def get_opportunity(
    opportunity_id: int, db: DbSession
) -> RealEstateOpportunityDetailRead | BusinessOpportunityDetailRead:
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
    if row is not None:
        opportunity, count = row
        return RealEstateOpportunityDetailRead(
            id=opportunity.id,
            type=opportunity.type,
            status=opportunity.status,
            title=opportunity.title,
            description=opportunity.description,
            location=opportunity.location,
            cover_image_url=opportunity.cover_image_url,
            images=opportunity.images,
            target_amount_cents=opportunity.target_amount_cents,
            committed_cents=opportunity.committed_cents,
            minimum_contribution_cents=opportunity.minimum_contribution_cents,
            deadline=opportunity.deadline,
            date_published=opportunity.date_published,
            promoter=to_read(opportunity.promoter, count),
            real_estate=RealEstateOpportunityRead.model_validate(
                opportunity.real_estate
            ),
            server_time=datetime.now(UTC),
        )

    equity_opportunity_id = db.scalar(
        select(Opportunity.id).where(
            Opportunity.id == opportunity_id,
            Opportunity.type == OpportunityType.EQUITY,
            Opportunity.status.in_(
                [OpportunityStatus.PUBLISHED, OpportunityStatus.CLOSED]
            ),
        )
    )
    if equity_opportunity_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oportunidad no disponible",
        )

    row = db.execute(
        select(Opportunity, published_projects_count)
        .join(Opportunity.business)
        .join(Opportunity.promoter)
        .options(
            contains_eager(Opportunity.business),
            contains_eager(Opportunity.promoter),
        )
        .where(
            Opportunity.id == opportunity_id,
            Opportunity.type == OpportunityType.EQUITY,
            Opportunity.status.in_(
                [OpportunityStatus.PUBLISHED, OpportunityStatus.CLOSED]
            ),
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oportunidad no disponible",
        )

    opportunity, count = row
    business = opportunity.business
    if business is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oportunidad no disponible",
        )
    target_amount = Decimal(opportunity.target_amount_cents)
    pre_investment_valuation = Decimal(business.pre_investment_valuation_cents)
    equity_offered = target_amount / (
        pre_investment_valuation + target_amount
    ) * Decimal(100)
    return BusinessOpportunityDetailRead(
        id=opportunity.id,
        type=opportunity.type,
        status=opportunity.status,
        title=opportunity.title,
        description=opportunity.description,
        location=opportunity.location,
        cover_image_url=opportunity.cover_image_url,
        images=opportunity.images,
        target_amount_cents=opportunity.target_amount_cents,
        committed_cents=opportunity.committed_cents,
        minimum_contribution_cents=opportunity.minimum_contribution_cents,
        date_published=opportunity.date_published,
        deadline=opportunity.deadline,
        promoter=to_read(opportunity.promoter, count),
        business=BusinessOpportunityRead(
            sector=business.sector,
            phase=business.phase,
            pre_investment_valuation_cents=business.pre_investment_valuation_cents,
            equity_offered=equity_offered,
        ),
        server_time=datetime.now(UTC),
    )
