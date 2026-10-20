"""create opportunities table

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


opportunity_type = sa.Enum(
    "real_estate",
    "equity",
    name="opportunity_type",
)
opportunity_type_column = sa.Enum(
    "real_estate",
    "equity",
    name="opportunity_type",
    create_type=False,
)


def upgrade() -> None:
    opportunity_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "opportunities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type", opportunity_type_column, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("cover_image_url", sa.String(length=2048), nullable=True),
        sa.Column("target_amount_cents", sa.Integer(), nullable=False),
        sa.Column("committed_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date_published", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_closed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("target_amount_cents >= 0", name="target_amount_non_negative"),
        sa.CheckConstraint("committed_cents >= 0", name="committed_amount_non_negative"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunities")),
    )


def downgrade() -> None:
    op.drop_table("opportunities")
    opportunity_type.drop(op.get_bind(), checkfirst=True)
