"""Afegeix la mida dels fitxers de la galeria d'oportunitats.

Revision ID: 447b697f2709
Revises: 4d6464f9f9ca
Create Date: 2026-11-22 15:36:42.894082
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '447b697f2709'
down_revision: Union[str, Sequence[str], None] = '4d6464f9f9ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "opportunity_images",
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        op.f("ck_opportunity_images_size_non_negative"),
        "opportunity_images",
        "size_bytes >= 0",
    )
    op.alter_column("opportunity_images", "size_bytes", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_opportunity_images_size_non_negative"),
        "opportunity_images",
        type_="check",
    )
    op.drop_column("opportunity_images", "size_bytes")
