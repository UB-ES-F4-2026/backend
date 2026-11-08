"""align opportunity status with US02.2.1

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-07 13:00:00.000000

Escrita a mano: autogenerate no detecta valores eliminados de un enum ni CHECK
nuevos en tablas existentes.
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def replace_status_type(values: tuple[str, ...]) -> None:
    """Recrea el enum opportunity_status con los valores indicados.

    PostgreSQL no permite eliminar valores de un enum, así que se crea uno nuevo
    y se convierte la columna.
    """
    labels = ", ".join(f"'{value}'" for value in values)
    op.execute("ALTER TYPE opportunity_status RENAME TO opportunity_status_old")
    op.execute(f"CREATE TYPE opportunity_status AS ENUM ({labels})")
    op.execute("ALTER TABLE opportunities ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE opportunities ALTER COLUMN status TYPE opportunity_status "
        "USING status::text::opportunity_status"
    )
    op.execute("ALTER TABLE opportunities ALTER COLUMN status SET DEFAULT 'published'")
    op.execute("DROP TYPE opportunity_status_old")


def upgrade() -> None:
    # «Financiación completada» se deduce de los importes; no es un estado guardado.
    op.execute("UPDATE opportunities SET status = 'published' WHERE status = 'funded'")
    # El catálogo ya trataba date_closed como cerrada: se refleja en el estado.
    op.execute(
        "UPDATE opportunities SET status = 'closed' "
        "WHERE date_closed IS NOT NULL AND status = 'published'"
    )
    replace_status_type(("draft", "published", "rejected", "closed"))

    op.drop_constraint(
        op.f('ck_opportunities_target_amount_non_negative'), 'opportunities', type_='check'
    )
    op.create_check_constraint(
        op.f('ck_opportunities_target_amount_positive'),
        'opportunities',
        'target_amount_cents > 0',
    )
    op.create_check_constraint(
        op.f('ck_opportunities_public_status_requires_date_published'),
        'opportunities',
        "status NOT IN ('published', 'closed') OR date_published IS NOT NULL",
    )
    op.create_check_constraint(
        op.f('ck_opportunities_closed_status_matches_date_closed'),
        'opportunities',
        "(status = 'closed') = (date_closed IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f('ck_opportunities_closed_status_matches_date_closed'), 'opportunities', type_='check'
    )
    op.drop_constraint(
        op.f('ck_opportunities_public_status_requires_date_published'),
        'opportunities',
        type_='check',
    )
    op.drop_constraint(
        op.f('ck_opportunities_target_amount_positive'), 'opportunities', type_='check'
    )
    op.create_check_constraint(
        op.f('ck_opportunities_target_amount_non_negative'),
        'opportunities',
        'target_amount_cents >= 0',
    )
    # Las filas convertidas en upgrade no se pueden distinguir: se quedan como están.
    replace_status_type(("draft", "published", "funded", "rejected", "closed"))
