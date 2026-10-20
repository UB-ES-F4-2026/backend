"""associate opportunities with their creator

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_index("ix_opportunities_user_id", "opportunities", ["user_id"])
    op.create_foreign_key(
        "fk_opportunities_user_id_users",
        "opportunities",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_opportunities_user_id_users",
        "opportunities",
        type_="foreignkey",
    )
    op.drop_index("ix_opportunities_user_id", table_name="opportunities")
    op.drop_column("opportunities", "user_id")
