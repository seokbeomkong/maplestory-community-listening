"""Index cumulative rankings by materialization slot.

Revision ID: 0005_cumulative_slot_index
Revises: 0004_source_backfill_state
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0005_cumulative_slot_index"
down_revision: str | None = "0004_source_backfill_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX cumulative_top_posts_slot_idx "
        "ON cumulative_top_posts (as_of_slot_kst)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX cumulative_top_posts_slot_idx")
