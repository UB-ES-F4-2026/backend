"""backfill wallets and constrain available balance

Revision ID: a6b27f4c91de
Revises: 921bcf34f7c2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6b27f4c91de"
down_revision: Union[str, Sequence[str], None] = "921bcf34f7c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "wallets",
        "available_cents",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        server_default=sa.text("0"),
    )
    op.execute(
        sa.text(
            "INSERT INTO wallets (user_id) "
            "SELECT users.id FROM users "
            "LEFT JOIN wallets ON wallets.user_id = users.id "
            "WHERE wallets.id IS NULL"
        )
    )
    op.create_check_constraint(
        op.f("ck_wallets_available_cents_non_negative"),
        "wallets",
        "available_cents >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_wallets_available_cents_non_negative"), "wallets", type_="check"
    )
    op.alter_column(
        "wallets",
        "available_cents",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        server_default=None,
    )