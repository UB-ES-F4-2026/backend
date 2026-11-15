"""create commitments and committed balance

Revision ID: 36d25506c764
Revises: a6b27f4c91de
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "36d25506c764"
down_revision: Union[str, Sequence[str], None] = "a6b27f4c91de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Els wallets existents comencen sense saldo compromès.
    op.add_column(
        "wallets",
        sa.Column(
            "committed_cents",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_wallets_committed_cents_non_negative"),
        "wallets",
        "committed_cents >= 0",
    )
    op.create_table(
        "commitments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount_cents > 0", name=op.f("ck_commitments_amount_cents_positive")
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_commitments_opportunity_id_opportunities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_commitments_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_commitments")),
    )
    op.create_index(
        op.f("ix_commitments_opportunity_id"), "commitments", ["opportunity_id"]
    )
    op.create_index(op.f("ix_commitments_user_id"), "commitments", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_commitments_user_id"), table_name="commitments")
    op.drop_index(op.f("ix_commitments_opportunity_id"), table_name="commitments")
    op.drop_table("commitments")
    op.drop_constraint(
        op.f("ck_wallets_committed_cents_non_negative"), "wallets", type_="check"
    )
    op.drop_column("wallets", "committed_cents")
