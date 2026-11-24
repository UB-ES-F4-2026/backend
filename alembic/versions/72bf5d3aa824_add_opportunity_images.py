"""Afegeix la galeria ordenada d'imatges d'oportunitats.

Revision ID: 72bf5d3aa824
Revises: 36d25506c764
Create Date: 2026-11-21 17:45:17.904608
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "72bf5d3aa824"
down_revision: Union[str, Sequence[str], None] = "36d25506c764"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "opportunity_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "position >= 0",
            name=op.f("ck_opportunity_images_position_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_opportunity_images_opportunity_id_opportunities"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity_images")),
        sa.UniqueConstraint("opportunity_id", "position", name="opportunity_position"),
        sa.UniqueConstraint("storage_key", name=op.f("uq_opportunity_images_storage_key")),
    )
    op.create_index(
        op.f("ix_opportunity_images_opportunity_id"),
        "opportunity_images",
        ["opportunity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_opportunity_images_opportunity_id"),
        table_name="opportunity_images",
    )
    op.drop_table("opportunity_images")
