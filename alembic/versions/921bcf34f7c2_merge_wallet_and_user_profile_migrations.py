"""merge wallet and user profile migrations

Revision ID: 921bcf34f7c2
Revises: 94a430e17ac4, fd3e5877ace3
Create Date: 2026-11-09 14:48:19.353533
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '921bcf34f7c2'
down_revision: Union[str, Sequence[str], None] = ('94a430e17ac4', 'fd3e5877ace3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
