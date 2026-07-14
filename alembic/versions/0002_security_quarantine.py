"""Add deterministic untrusted-content quarantine storage.

Revision ID: 0002_security_quarantine
Revises: 0001_core_collection
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0002_security_quarantine"
down_revision: str | None = "0001_core_collection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE security_quarantine (
          id uuid PRIMARY KEY,
          source_kind text NOT NULL,
          source_ref text NOT NULL,
          content_hash char(64) NOT NULL,
          findings jsonb NOT NULL,
          risk_score integer NOT NULL,
          quarantined_at timestamptz NOT NULL DEFAULT now(),
          review_state text NOT NULL,
          reviewer text,
          note text,
          released_at timestamptz,
          CONSTRAINT security_quarantine_source_content_key
            UNIQUE (source_kind, source_ref, content_hash),
          CONSTRAINT security_quarantine_risk_score_check
            CHECK (risk_score BETWEEN 0 AND 100),
          CONSTRAINT security_quarantine_review_state_check
            CHECK (review_state IN ('pending', 'released', 'confirmed')),
          CONSTRAINT security_quarantine_source_kind_check
            CHECK (source_kind ~ '^[a-z][a-z0-9_]{0,63}$'),
          CONSTRAINT security_quarantine_source_ref_check
            CHECK (length(source_ref) BETWEEN 1 AND 512 AND source_ref = btrim(source_ref)),
          CONSTRAINT security_quarantine_findings_array_check
            CHECK (jsonb_typeof(findings) = 'array'),
          CONSTRAINT security_quarantine_review_audit_check CHECK (
            (review_state = 'pending' AND reviewer IS NULL AND note IS NULL
              AND released_at IS NULL)
            OR
            (review_state = 'released' AND reviewer IS NOT NULL AND btrim(reviewer) <> ''
              AND note IS NOT NULL AND btrim(note) <> '' AND released_at IS NOT NULL)
            OR
            (review_state = 'confirmed' AND reviewer IS NOT NULL AND btrim(reviewer) <> ''
              AND note IS NOT NULL AND btrim(note) <> '' AND released_at IS NULL)
          )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE security_quarantine")
