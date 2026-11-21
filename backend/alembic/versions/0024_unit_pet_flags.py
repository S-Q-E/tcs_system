"""Add explicit pet flags to leasing units.

Revision ID: 0024_unit_pet_flags
Revises: 0023_units_slots_bookings
Create Date: 2026-11-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_unit_pet_flags"
down_revision = "0023_units_slots_bookings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tcs_crm_units",
        sa.Column("allows_dogs", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "tcs_crm_units",
        sa.Column("allows_cats", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Backfill from the free-text policy. "No pets" and "no dogs/cats" stay false;
    # "Cats only" / "Only cats" -> cats=true, dogs=false; "Cats and small dogs" -> both.
    op.execute(
        """
        UPDATE tcs_crm_units
           SET allows_dogs = (
                   lower(coalesce(pets_policy, '')) LIKE '%dog%'
                   AND lower(coalesce(pets_policy, '')) NOT LIKE '%no dog%'
                   AND lower(coalesce(pets_policy, '')) NOT LIKE 'no pets%'
               ),
               allows_cats = (
                   lower(coalesce(pets_policy, '')) LIKE '%cat%'
                   AND lower(coalesce(pets_policy, '')) NOT LIKE '%no cat%'
                   AND lower(coalesce(pets_policy, '')) NOT LIKE 'no pets%'
               )
        """
    )


def downgrade() -> None:
    op.drop_column("tcs_crm_units", "allows_cats")
    op.drop_column("tcs_crm_units", "allows_dogs")
