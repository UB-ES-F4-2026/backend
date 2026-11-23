"""Alinea les enumeracions empresarials amb el contracte de Trello.

Revision ID: e9a7d4c03b12
Revises: 447b697f2709
Create Date: 2026-11-22 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e9a7d4c03b12"
down_revision: Union[str, Sequence[str], None] = "447b697f2709"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adapta sectors i fases als valors definitius de la US 06.1.2."""
    op.execute(
        """
        CREATE TYPE business_sector_new AS ENUM (
            'technology',
            'industry',
            'food_and_beverage',
            'commerce',
            'health',
            'energy',
            'tourism_and_leisure',
            'other_services'
        )
        """
    )
    op.execute(
        """
        CREATE TYPE business_phase_new AS ENUM (
            'idea',
            'launch',
            'growth',
            'consolidated'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE public.business_opportunities
        ALTER COLUMN sector TYPE business_sector_new
        USING (
            CASE sector::text
                WHEN 'fintech' THEN 'technology'
                WHEN 'saas' THEN 'technology'
                WHEN 'ai' THEN 'technology'
                WHEN 'education' THEN 'technology'
                WHEN 'media' THEN 'technology'
                WHEN 'biotech' THEN 'health'
                WHEN 'cleantech' THEN 'energy'
                WHEN 'agritech' THEN 'food_and_beverage'
                WHEN 'foodtech' THEN 'food_and_beverage'
                WHEN 'd2c' THEN 'commerce'
                WHEN 'logistic' THEN 'other_services'
                WHEN 'tourism' THEN 'tourism_and_leisure'
                WHEN 'other' THEN 'other_services'
                ELSE sector::text
            END
        )::business_sector_new
        """
    )
    op.execute(
        """
        ALTER TABLE public.business_opportunities
        ALTER COLUMN phase TYPE business_phase_new
        USING (
            CASE phase::text
                WHEN 'pre_seed' THEN 'idea'
                WHEN 'seed' THEN 'launch'
                WHEN 'early' THEN 'launch'
                WHEN 'late' THEN 'consolidated'
                ELSE phase::text
            END
        )::business_phase_new
        """
    )
    op.execute("DROP TYPE business_sector")
    op.execute("DROP TYPE business_phase")
    op.execute("ALTER TYPE business_sector_new RENAME TO business_sector")
    op.execute("ALTER TYPE business_phase_new RENAME TO business_phase")


def downgrade() -> None:
    """Recupera les enumeracions empresarials anteriors."""
    op.execute(
        """
        CREATE TYPE business_sector_old AS ENUM (
            'fintech',
            'industry',
            'saas',
            'health',
            'biotech',
            'cleantech',
            'agritech',
            'foodtech',
            'd2c',
            'education',
            'media',
            'tourism',
            'logistic',
            'ai',
            'other'
        )
        """
    )
    op.execute(
        """
        CREATE TYPE business_phase_old AS ENUM (
            'pre_seed',
            'seed',
            'early',
            'growth',
            'late'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE public.business_opportunities
        ALTER COLUMN sector TYPE business_sector_old
        USING (
            CASE sector::text
                WHEN 'technology' THEN 'fintech'
                WHEN 'food_and_beverage' THEN 'foodtech'
                WHEN 'commerce' THEN 'd2c'
                WHEN 'energy' THEN 'cleantech'
                WHEN 'tourism_and_leisure' THEN 'tourism'
                WHEN 'other_services' THEN 'other'
                ELSE sector::text
            END
        )::business_sector_old
        """
    )
    op.execute(
        """
        ALTER TABLE public.business_opportunities
        ALTER COLUMN phase TYPE business_phase_old
        USING (
            CASE phase::text
                WHEN 'idea' THEN 'pre_seed'
                WHEN 'launch' THEN 'seed'
                WHEN 'consolidated' THEN 'late'
                ELSE phase::text
            END
        )::business_phase_old
        """
    )
    op.execute("DROP TYPE business_sector")
    op.execute("DROP TYPE business_phase")
    op.execute("ALTER TYPE business_sector_old RENAME TO business_sector")
    op.execute("ALTER TYPE business_phase_old RENAME TO business_phase")
