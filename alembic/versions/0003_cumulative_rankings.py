"""Add source-backed cumulative ranking materialization.

Revision ID: 0003_cumulative_rankings
Revises: 0002_security_quarantine
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0003_cumulative_rankings"
down_revision: str | None = "0002_security_quarantine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE cumulative_top_posts (
          analysis_unit text NOT NULL,
          metric text NOT NULL,
          as_of_slot_kst timestamptz NOT NULL,
          rank integer NOT NULL,
          board_id integer NOT NULL,
          post_id bigint NOT NULL,
          metric_value bigint NOT NULL,
          config_version char(64) NOT NULL,
          CONSTRAINT cumulative_top_posts_pkey
            PRIMARY KEY (analysis_unit, metric, as_of_slot_kst, post_id),
          CONSTRAINT cumulative_top_posts_unit_metric_slot_rank_key
            UNIQUE (analysis_unit, metric, as_of_slot_kst, rank),
          CONSTRAINT cumulative_top_posts_post_fkey
            FOREIGN KEY (board_id, post_id) REFERENCES posts(board_id, post_id),
          CONSTRAINT cumulative_top_posts_metric_check
            CHECK (metric IN ('views', 'recommendations', 'comments')),
          CONSTRAINT cumulative_top_posts_rank_check
            CHECK (rank > 0),
          CONSTRAINT cumulative_top_posts_metric_value_check
            CHECK (metric_value >= 0)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX cumulative_latest_idx
          ON cumulative_top_posts (analysis_unit, metric, as_of_slot_kst DESC, rank)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE cumulative_top_posts")
