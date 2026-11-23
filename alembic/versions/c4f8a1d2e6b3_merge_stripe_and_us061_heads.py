"""Uneix les migracions de Stripe i la US 06.1.

Revision ID: c4f8a1d2e6b3
Revises: 61b6621b89c6, e9a7d4c03b12
Create Date: 2026-11-22 22:05:00.000000
"""
from typing import Sequence, Union


revision: str = "c4f8a1d2e6b3"
down_revision: Union[str, Sequence[str], None] = (
    "61b6621b89c6",
    "e9a7d4c03b12",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Uneix branques de migració que no alteren l'esquema."""


def downgrade() -> None:
    """Separa les branques de migració en desfer la unió."""
