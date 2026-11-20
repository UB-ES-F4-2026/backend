"""Update business sector types

Revision ID: 7ea1a0d4de53
Revises: 0f4afe25bff8
Create Date: 2026-11-19 14:29:36.274662
"""
from typing import Sequence, Union

from alembic import op


revision: str = '7ea1a0d4de53'
down_revision: Union[str, Sequence[str], None] = '0f4afe25bff8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TYPE business_sector_new AS ENUM (
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
        ALTER TABLE public.business_opportunities
        ALTER COLUMN sector TYPE business_sector_new
        USING (
            CASE sector::text
                WHEN 'healthtech' THEN 'health'
                WHEN 'edtech' THEN 'education'
                ELSE sector::text
            END
        )::business_sector_new
        """
    )
    op.execute("DROP TYPE business_sector")
    op.execute("ALTER TYPE business_sector_new RENAME TO business_sector")


def downgrade() -> None:
    op.execute(
        """
        CREATE TYPE business_sector_old AS ENUM (
            'fintech',
            'saas',
            'healthtech',
            'biotech',
            'cleantech',
            'agritech',
            'foodtech',
            'd2c',
            'edtech',
            'media',
            'ai',
            'other'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE public.business_opportunities
        ALTER COLUMN sector TYPE business_sector_old
        USING (
            CASE sector::text
                WHEN 'health' THEN 'healthtech'
                WHEN 'education' THEN 'edtech'
                WHEN 'industry' THEN 'other'
                WHEN 'tourism' THEN 'other'
                WHEN 'logistic' THEN 'other'
                ELSE sector::text
            END
        )::business_sector_old
        """
    )
    op.execute("DROP TYPE business_sector")
    op.execute("ALTER TYPE business_sector_old RENAME TO business_sector")
