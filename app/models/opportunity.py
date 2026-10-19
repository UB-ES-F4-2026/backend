"""Investment opportunities offered by the platform."""
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OpportunityType(str, Enum):
    REAL_ESTATE = "real_estate"
    EQUITY = "equity"


class OpportunityStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    FUNDED = "funded"
    REJECTED = "rejected"
    CLOSED = "closed"


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint("target_amount_cents >= 0", name="target_amount_non_negative"),
        CheckConstraint("committed_cents >= 0", name="committed_amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    type: Mapped[OpportunityType] = mapped_column(
        SqlEnum(
            OpportunityType,
            name="opportunity_type",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    status: Mapped[OpportunityStatus] = mapped_column(
        SqlEnum(
            OpportunityStatus,
            name="opportunity_status",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=OpportunityStatus.PUBLISHED,  # Canviar quan afegim el rol de verificador
        server_default=OpportunityStatus.PUBLISHED.value,
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(255))
    cover_image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    target_amount_cents: Mapped[int] = mapped_column(Integer)
    committed_cents: Mapped[int] = mapped_column(Integer, default=0)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    date_published: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    date_closed: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
