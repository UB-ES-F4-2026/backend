"""record Stripe wallet deposits idempotently

Revision ID: d36a81c4f207
Revises: 94a430e17ac4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d36a81c4f207"
down_revision: Union[str, Sequence[str], None] = "94a430e17ac4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wallet_deposits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stripe_event_id", sa.String(length=255), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="eur", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_cents > 0", name="ck_wallet_deposits_amount_positive"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_wallet_deposits_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_wallet_deposits"),
        sa.UniqueConstraint("stripe_event_id", name="uq_wallet_deposits_stripe_event_id"),
        sa.UniqueConstraint(
            "stripe_payment_intent_id", name="uq_wallet_deposits_stripe_payment_intent_id"
        ),
    )
    op.create_index(
        "ix_wallet_deposits_user_id", "wallet_deposits", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_wallet_deposits_user_id", table_name="wallet_deposits")
    op.drop_table("wallet_deposits")