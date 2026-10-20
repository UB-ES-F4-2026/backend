"""add status to opportunities

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


opportunity_status = sa.Enum(
    "draft", "published", "funded", "rejected", "closed", name="opportunity_status"
)


def upgrade() -> None:
    opportunity_status.create(op.get_bind(), checkfirst=True)
    status_column = sa.Enum(
        "draft",
        "published",
        "funded",
        "rejected",
        "closed",
        name="opportunity_status",
        create_type=False,
    )
    op.add_column(
        "opportunities",
        sa.Column("status", status_column, nullable=False, server_default="published"),
    )


def downgrade() -> None:
    op.drop_column("opportunities", "status")
    opportunity_status.drop(op.get_bind(), checkfirst=True)
