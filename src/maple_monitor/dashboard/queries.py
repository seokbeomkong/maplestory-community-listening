from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Final

import pandas as pd
from sqlalchemy import Engine, text


_ANALYSIS_UNIT_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_METRICS: Final = frozenset({"views", "recommendations", "comments"})
_DASHBOARD_ROW_LIMIT: Final = 50

_CUMULATIVE_QUERY = text(
    """
    WITH selected_slot AS (
      SELECT max(ranked.as_of_slot_kst) AS as_of_slot_kst
      FROM cumulative_top_posts AS ranked
      WHERE ranked.analysis_unit = :analysis_unit
        AND ranked.metric = :metric
        AND (
          CAST(:as_of_slot AS timestamptz) IS NULL
          OR ranked.as_of_slot_kst <= CAST(:as_of_slot AS timestamptz)
        )
    )
    SELECT
      ranked.rank,
      post.title,
      ranked.metric_value,
      post.published_at,
      post.source_url,
      ranked.as_of_slot_kst,
      ranked.config_version
    FROM cumulative_top_posts AS ranked
    JOIN selected_slot
      ON selected_slot.as_of_slot_kst = ranked.as_of_slot_kst
    JOIN posts AS post
      ON post.board_id = ranked.board_id
     AND post.post_id = ranked.post_id
    WHERE ranked.analysis_unit = :analysis_unit
      AND ranked.metric = :metric
      AND ranked.rank <= :row_limit
    ORDER BY ranked.rank
    LIMIT :row_limit
    """
)


def _validated_analysis_unit(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("analysis_unit must be a string")
    if _ANALYSIS_UNIT_PATTERN.fullmatch(value) is None:
        raise ValueError("analysis_unit must be a bounded lowercase slug")
    return value


def _validated_metric(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("metric must be a string")
    if value not in _METRICS:
        raise ValueError("metric is not supported")
    return value


def _normalized_optional_as_of(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError("as_of_slot must be a datetime or None")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of_slot must be timezone-aware")
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError) as exc:
        raise ValueError("as_of_slot is outside the supported database range") from exc


def load_cumulative_top(
    engine: Engine,
    analysis_unit: str,
    metric: str,
    as_of_slot: datetime | None = None,
) -> pd.DataFrame:
    """Load one bounded, materialized cumulative ranking without dynamic SQL values."""

    params = {
        "analysis_unit": _validated_analysis_unit(analysis_unit),
        "metric": _validated_metric(metric),
        "as_of_slot": _normalized_optional_as_of(as_of_slot),
        "row_limit": _DASHBOARD_ROW_LIMIT,
    }
    return pd.read_sql_query(_CUMULATIVE_QUERY, engine, params=params)
