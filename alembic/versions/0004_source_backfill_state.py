"""Add resumable per-source backfill state.

Revision ID: 0004_source_backfill_state
Revises: 0003_cumulative_rankings
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0004_source_backfill_state"
down_revision: str | None = "0003_cumulative_rankings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE source_backfill_states (
          source_key text PRIMARY KEY,
          next_page integer NOT NULL,
          checkpoint_post_id bigint,
          complete boolean NOT NULL DEFAULT false,
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT source_backfill_states_next_page_check CHECK (next_page > 0),
          CONSTRAINT source_backfill_states_source_key_check CHECK (
            source_key IN (
              'warrior', 'magician', 'archer', 'thief',
              'pirate', 'free', 'qna', 'tips'
            )
          )
        )
        """
    )
    op.execute(
        "CREATE INDEX source_backfill_states_updated_at_idx "
        "ON source_backfill_states (updated_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE source_backfill_states")
