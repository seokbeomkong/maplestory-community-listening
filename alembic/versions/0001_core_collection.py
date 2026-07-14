"""Create replay-safe collection core tables.

Revision ID: 0001_core_collection
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0001_core_collection"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE boards (
          id integer PRIMARY KEY,
          name text NOT NULL,
          kind text NOT NULL CHECK (kind IN ('job', 'free', 'info'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE posts (
          board_id integer NOT NULL REFERENCES boards(id),
          post_id bigint NOT NULL,
          analysis_unit text NOT NULL,
          title text NOT NULL,
          published_at timestamptz NOT NULL,
          source_url text NOT NULL,
          is_notice boolean NOT NULL DEFAULT false,
          is_ad boolean NOT NULL DEFAULT false,
          current_category text,
          last_seen_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (board_id, post_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE post_metric_snapshots (
          board_id integer NOT NULL,
          post_id bigint NOT NULL,
          observed_at_slot_kst timestamptz NOT NULL,
          observed_at_actual timestamptz NOT NULL DEFAULT now(),
          views bigint NOT NULL CHECK (views >= 0),
          recommendations integer NOT NULL CHECK (recommendations >= 0),
          comments integer NOT NULL CHECK (comments >= 0),
          config_version char(64) NOT NULL,
          PRIMARY KEY (board_id, post_id, observed_at_slot_kst),
          FOREIGN KEY (board_id, post_id) REFERENCES posts(board_id, post_id)
        ) PARTITION BY RANGE (observed_at_slot_kst)
        """
    )
    op.execute(
        """
        CREATE TABLE post_metric_snapshots_default
          PARTITION OF post_metric_snapshots DEFAULT
        """
    )
    op.execute(
        """
        CREATE TABLE collection_runs (
          id uuid PRIMARY KEY,
          job_type text NOT NULL,
          scheduled_at_slot_kst timestamptz NOT NULL,
          status text NOT NULL CHECK (status IN ('running', 'succeeded', 'partial', 'failed')),
          config_version char(64) NOT NULL,
          started_at timestamptz NOT NULL,
          finished_at timestamptz,
          diagnostics jsonb NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute(
        """
        CREATE TABLE run_slots (
          job_type text NOT NULL,
          scheduled_at_slot_kst timestamptz NOT NULL,
          run_id uuid NOT NULL REFERENCES collection_runs(id),
          PRIMARY KEY (job_type, scheduled_at_slot_kst)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE work_items (
          id bigserial PRIMARY KEY,
          task_key text NOT NULL UNIQUE,
          kind text NOT NULL,
          state text NOT NULL CHECK (state IN ('pending', 'leased', 'succeeded', 'retry', 'dead')),
          priority integer NOT NULL DEFAULT 100,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          payload_hash char(64),
          attempts integer NOT NULL DEFAULT 0,
          available_at timestamptz NOT NULL,
          lease_owner text,
          lease_until timestamptz,
          last_error text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX work_items_claim_idx
          ON work_items (state, priority, available_at, id)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE work_items")
    op.execute("DROP TABLE run_slots")
    op.execute("DROP TABLE collection_runs")
    op.execute("DROP TABLE post_metric_snapshots_default")
    op.execute("DROP TABLE post_metric_snapshots")
    op.execute("DROP TABLE posts")
    op.execute("DROP TABLE boards")
