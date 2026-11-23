"""unir migracions de Stripe i dev

Revision ID: 61b6621b89c6
Revises: 3b4692f967ff, 84b481c94829
Create Date: 2026-11-22 15:10:17.295986
"""
from typing import Sequence, Union

revision: str = '61b6621b89c6'
down_revision: Union[str, Sequence[str], None] = ('3b4692f967ff', '84b481c94829')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
