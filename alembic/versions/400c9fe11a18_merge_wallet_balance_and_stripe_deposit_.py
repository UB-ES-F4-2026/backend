"""merge wallet balance and Stripe deposit migrations

Revision ID: 400c9fe11a18
Revises: a6b27f4c91de, d36a81c4f207
Create Date: 2026-11-10 11:35:43.540953
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '400c9fe11a18'
down_revision: Union[str, Sequence[str], None] = ('a6b27f4c91de', 'd36a81c4f207')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
