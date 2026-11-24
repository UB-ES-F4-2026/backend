"""widen opportunity amounts to bigint

Revision ID: 24ca1e48a929
Revises: c4f8a1d2e6b3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "24ca1e48a929"
down_revision: Union[str, Sequence[str], None] = "c4f8a1d2e6b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Imports en cèntims que un enter de 32 bits limitava a 21.474.836,47 €.
AMOUNT_COLUMNS = (
    ("opportunities", "target_amount_cents", False),
    ("opportunities", "committed_cents", False),
    ("opportunities", "minimum_contribution_cents", True),
    ("business_opportunities", "pre_investment_valuation_cents", False),
)


def upgrade() -> None:
    for table, column, nullable in AMOUNT_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=nullable,
        )


def downgrade() -> None:
    # PostgreSQL rebutja el canvi si algun import ja no cap en 32 bits.
    for table, column, nullable in reversed(AMOUNT_COLUMNS):
        op.alter_column(
            table,
            column,
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=nullable,
        )
