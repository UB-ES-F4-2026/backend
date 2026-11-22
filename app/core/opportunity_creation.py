"""Creació comuna d'oportunitats pendents de revisió."""
from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.core.commitments import reserve_funds
from app.core.media import (
    StagedImage,
    StoredImage,
    delete_stored_images,
    persist_staged_images,
)
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.opportunity_image import OpportunityImage
from app.schemas.opportunity import OpportunityCreate


def create_pending_opportunity(
    db: Session,
    *,
    user_id: int,
    body: OpportunityCreate,
    staged_images: Iterable[StagedImage],
) -> tuple[Opportunity, list[StoredImage]]:
    """Crea l'oportunitat, les seves imatges i la reserva dins la transacció."""
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

    stored_images: list[StoredImage] = []
    try:
        stored_images = persist_staged_images(staged_images, opportunity.id)
        opportunity.images = [
            OpportunityImage(
                storage_key=stored_image.storage_key,
                content_type=stored_image.content_type,
                size_bytes=stored_image.size_bytes,
                position=position,
            )
            for position, stored_image in enumerate(stored_images)
        ]
        db.flush()
    except Exception:
        delete_stored_images(stored_images)
        raise
    return opportunity, stored_images
