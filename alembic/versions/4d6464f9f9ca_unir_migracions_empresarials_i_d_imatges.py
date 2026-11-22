"""unir migracions empresarials i d'imatges

Revision ID: 4d6464f9f9ca
Revises: 3b4692f967ff, 72bf5d3aa824
Create Date: 2026-11-22 15:00:38.465126
"""
from typing import Sequence, Union

revision: str = '4d6464f9f9ca'
down_revision: Union[str, Sequence[str], None] = ('3b4692f967ff', '72bf5d3aa824')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
