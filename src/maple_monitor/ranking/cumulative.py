from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import text
from sqlalchemy.orm import Session


_ANALYSIS_UNIT: Final = "hero"
_CONFIG_VERSION_PATTERN: Final = re.compile(r"[0-9a-f]{64}\Z")
_MAX_WINDOW_DAYS: Final = 365
_MAX_TOP_N: Final = 500
_ADVISORY_LOCK_KEY: Final = 0x4D41504C4552414E

_RANKING_INSERT = text(
    """
    WITH eligible AS (
      SELECT
        post.analysis_unit,
        post.board_id,
        post.post_id,
        post.published_at,
        latest.views,
        latest.recommendations,
        latest.comments
      FROM posts AS post
      JOIN LATERAL (
        SELECT
          snapshot.views,
          snapshot.recommendations,
          snapshot.comments
        FROM post_metric_snapshots AS snapshot
        WHERE snapshot.board_id = post.board_id
          AND snapshot.post_id = post.post_id
          AND snapshot.observed_at_slot_kst <= :as_of_slot
        ORDER BY snapshot.observed_at_slot_kst DESC
        LIMIT 1
      ) AS latest ON TRUE
      WHERE post.analysis_unit = :analysis_unit
        AND post.is_notice IS FALSE
        AND post.is_ad IS FALSE
        AND post.published_at >= :cutoff
        AND post.published_at <= :as_of_slot
        AND NOT EXISTS (
          SELECT 1
          FROM security_quarantine AS quarantine
          WHERE quarantine.source_kind = 'title'
            AND quarantine.source_ref = concat('post:', post.board_id, ':', post.post_id)
            AND quarantine.review_state IN ('pending', 'confirmed')
        )
    ),
    expanded AS (
      SELECT
        eligible.analysis_unit,
        metric_values.metric,
        eligible.board_id,
        eligible.post_id,
        eligible.published_at,
        metric_values.metric_value
      FROM eligible
      CROSS JOIN LATERAL (
        VALUES
          ('views'::text, eligible.views::bigint),
          ('recommendations'::text, eligible.recommendations::bigint),
          ('comments'::text, eligible.comments::bigint)
      ) AS metric_values(metric, metric_value)
    ),
    ranked AS (
      SELECT
        expanded.*,
        row_number() OVER (
          PARTITION BY expanded.analysis_unit, expanded.metric
          ORDER BY
            expanded.metric_value DESC,
            expanded.published_at DESC,
            expanded.post_id DESC,
            expanded.board_id DESC
        ) AS rank
      FROM expanded
    )
    INSERT INTO cumulative_top_posts (
      analysis_unit,
      metric,
      as_of_slot_kst,
      rank,
      board_id,
      post_id,
      metric_value,
      config_version
    )
    SELECT
      ranked.analysis_unit,
      ranked.metric,
      :as_of_slot,
      ranked.rank,
      ranked.board_id,
      ranked.post_id,
      ranked.metric_value,
      :config_version
    FROM ranked
    WHERE ranked.rank <= :top_n
    ORDER BY ranked.metric, ranked.rank
    RETURNING post_id
    """
)


def _bounded_integer(value: object, *, name: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not 1 <= value <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


def _normalized_as_of(value: object, *, window_days: int) -> tuple[datetime, datetime]:
    if not isinstance(value, datetime):
        raise TypeError("as_of_slot must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of_slot must be timezone-aware")
    try:
        normalized = value.astimezone(UTC)
        cutoff = normalized - timedelta(days=window_days)
    except (OverflowError, ValueError) as exc:
        raise ValueError("as_of_slot is outside the supported database range") from exc
    return normalized, cutoff


def _validated_config_version(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("config_version must be a string")
    if _CONFIG_VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError("config_version must be a lowercase SHA-256 hex digest")
    return value


def refresh_cumulative(
    session: Session,
    as_of_slot: datetime,
    window_days: int,
    top_n: int,
    config_version: str,
) -> int:
    """Replace the Hero cumulative rankings inside the caller-owned transaction."""

    validated_window_days = _bounded_integer(
        window_days,
        name="window_days",
        maximum=_MAX_WINDOW_DAYS,
    )
    validated_top_n = _bounded_integer(top_n, name="top_n", maximum=_MAX_TOP_N)
    normalized_as_of, cutoff = _normalized_as_of(
        as_of_slot,
        window_days=validated_window_days,
    )
    validated_config_version = _validated_config_version(config_version)

    session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": _ADVISORY_LOCK_KEY},
    )
    session.execute(
        text(
            "DELETE FROM cumulative_top_posts "
            "WHERE analysis_unit = :analysis_unit AND as_of_slot_kst = :as_of_slot"
        ),
        {"analysis_unit": _ANALYSIS_UNIT, "as_of_slot": normalized_as_of},
    )
    inserted_rows = session.execute(
        _RANKING_INSERT,
        {
            "analysis_unit": _ANALYSIS_UNIT,
            "as_of_slot": normalized_as_of,
            "cutoff": cutoff,
            "top_n": validated_top_n,
            "config_version": validated_config_version,
        },
    ).all()
    session.execute(
        text(
            "INSERT INTO work_items "
            "(task_key, kind, state, payload, available_at) "
            "SELECT DISTINCT "
            "concat('detail:', ranked.board_id, ':', ranked.post_id, ':', 'deep-v1'), "
            "'detail_fetch', "
            "'pending', "
            "jsonb_build_object('board_id', ranked.board_id, 'post_id', ranked.post_id), "
            ":available_at "
            "FROM cumulative_top_posts AS ranked "
            "WHERE ranked.analysis_unit = :analysis_unit "
            "AND ranked.as_of_slot_kst = :as_of_slot "
            "ON CONFLICT (task_key) DO NOTHING"
        ),
        {
            "analysis_unit": _ANALYSIS_UNIT,
            "as_of_slot": normalized_as_of,
            "available_at": normalized_as_of,
        },
    )
    return len(inserted_rows)
