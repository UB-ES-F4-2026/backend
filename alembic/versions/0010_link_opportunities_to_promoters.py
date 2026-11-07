"""link opportunities to their promoting entity

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-07 14:00:00.000000

Toda oportunidad debe pertenecer a una entidad promotora: la clave foránea pasa
de users.id a promoting_entities.user_id (mismo valor) y deja de ser nulable.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Decisión del equipo: se eliminan las oportunidades sin entidad promotora
    # (o sin usuario). Sus datos inmobiliarios se borran por ON DELETE CASCADE.
    op.execute(
        """
        DELETE FROM opportunities AS o
        WHERE o.user_id IS NULL
           OR NOT EXISTS (
               SELECT 1 FROM promoting_entities AS p WHERE p.user_id = o.user_id
           )
        """
    )
    op.drop_constraint(
        op.f('fk_opportunities_user_id_users'), 'opportunities', type_='foreignkey'
    )
    op.alter_column('opportunities', 'user_id', existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key(
        op.f('fk_opportunities_user_id_promoting_entities'),
        'opportunities',
        'promoting_entities',
        ['user_id'],
        ['user_id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    # Las oportunidades eliminadas en upgrade no se recuperan.
    op.drop_constraint(
        op.f('fk_opportunities_user_id_promoting_entities'), 'opportunities', type_='foreignkey'
    )
    op.alter_column('opportunities', 'user_id', existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key(
        op.f('fk_opportunities_user_id_users'),
        'opportunities',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE',
    )
