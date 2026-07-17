from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Final

import pandas as pd

from maple_monitor.dashboard.export_data import ExportBundle
from maple_monitor.sources import JOB_ANALYSIS_UNITS


_METRICS: Final = frozenset({"views", "recommendations", "comments"})
_NON_JOB_UNITS: Final = frozenset({"free", "qna", "tips"})


@dataclass(frozen=True)
class WindowSelection:
    rows: pd.DataFrame
    requested_hours: int
    effective_hours: int
    fallback_reason: str | None
    start: pd.Timestamp
    end: pd.Timestamp


@dataclass(frozen=True)
class CollectionHealth:
    total_runs: int
    succeeded_runs: int
    failed_runs: int
    partial_runs: int
    success_rate: float
    latest_slot: pd.Timestamp | None
    failed: pd.DataFrame


@dataclass(frozen=True)
class SourcePeriod:
    start: pd.Timestamp
    end: pd.Timestamp

    @property
    def label(self) -> str:
        start = self.start.tz_convert("Asia/Seoul").strftime("%Y.%m.%d")
        end = self.end.tz_convert("Asia/Seoul").strftime("%Y.%m.%d")
        return f"{start}–{end} 게시물"


def source_period(rows: pd.DataFrame) -> SourcePeriod:
    if rows.empty or "published_at" not in rows:
        raise ValueError("published rows are required")
    published = pd.to_datetime(rows["published_at"], utc=True, errors="raise")
    return SourcePeriod(start=pd.Timestamp(published.min()), end=pd.Timestamp(published.max()))


def _period_label(hours: int) -> str:
    if hours == 24:
        return "24시간"
    if hours % 24 == 0:
        return f"{hours // 24}일"
    return f"{hours}시간"


def _as_of(posts: pd.DataFrame) -> pd.Timestamp:
    if posts.empty:
        raise ValueError("posts must not be empty")
    column = "observed_at_slot_kst" if "observed_at_slot_kst" in posts else "published_at"
    value = posts[column].max()
    if pd.isna(value):
        raise ValueError("posts must contain a factual timestamp")
    return pd.Timestamp(value)


def _rows_since(
    posts: pd.DataFrame,
    analysis_unit: str,
    *,
    end: pd.Timestamp,
    hours: int,
) -> pd.DataFrame:
    start = end - timedelta(hours=hours)
    mask = (posts["analysis_unit"] == analysis_unit) & (posts["published_at"] >= start)
    return posts.loc[mask].sort_values(["published_at", "post_id"], ascending=[False, False]).copy()


def select_window(
    posts: pd.DataFrame,
    analysis_unit: str,
    *,
    hours: int,
    fallback_hours: int | None = None,
    minimum: int = 0,
) -> WindowSelection:
    """Select one board-specific publication window with an explicit sparse fallback."""

    if hours <= 0 or minimum < 0:
        raise ValueError("hours must be positive and minimum must be non-negative")
    if fallback_hours is not None and fallback_hours < hours:
        raise ValueError("fallback_hours must not be shorter than hours")
    end = _as_of(posts)
    rows = _rows_since(posts, analysis_unit, end=end, hours=hours)
    effective_hours = hours
    fallback_reason = None
    if fallback_hours is not None and len(rows) < minimum:
        rows = _rows_since(posts, analysis_unit, end=end, hours=fallback_hours)
        effective_hours = fallback_hours
        fallback_reason = f"{_period_label(hours)} 표본 부족"
    return WindowSelection(
        rows=rows,
        requested_hours=hours,
        effective_hours=effective_hours,
        fallback_reason=fallback_reason,
        start=end - timedelta(hours=effective_hours),
        end=end,
    )


def rank_posts(rows: pd.DataFrame, metric: str, *, limit: int = 10) -> pd.DataFrame:
    """Rank posts by one factual engagement counter without a composite score."""

    if metric not in _METRICS:
        raise ValueError("unsupported engagement metric")
    if limit <= 0:
        raise ValueError("limit must be positive")
    columns = [
        "title",
        "comments",
        "recommendations",
        "views",
        "published_at",
        "source_url",
    ]
    if rows.empty:
        return rows.reindex(columns=columns).copy()
    return (
        rows.sort_values([metric, "published_at", "post_id"], ascending=[False, False, False])
        .head(limit)[columns]
        .reset_index(drop=True)
    )


def engagement_totals(rows: pd.DataFrame) -> dict[str, int]:
    """Return separate factual engagement totals for one evidence set."""

    return {
        "posts": len(rows),
        "comments": int(rows["comments"].sum()),
        "recommendations": int(rows["recommendations"].sum()),
        "views": int(rows["views"].sum()),
    }


def _job_labels() -> dict[str, str]:
    labels: dict[str, str] = {}
    for categories in JOB_ANALYSIS_UNITS.values():
        for label, unit in categories.items():
            if not unit.endswith("_other"):
                labels[unit] = label
    return labels


def job_comparison(
    posts: pd.DataFrame,
    *,
    hours: int = 168,
    fallback_hours: int = 720,
    minimum: int = 5,
) -> pd.DataFrame:
    """Compare collected jobs with both raw totals and per-post rates."""

    labels = _job_labels()
    units = sorted(set(posts["analysis_unit"]) - _NON_JOB_UNITS)
    columns = [
        "analysis_unit",
        "job",
        "sample_size",
        "total_comments",
        "comments_per_post",
        "total_recommendations",
        "recommendations_per_post",
        "total_views",
        "views_per_post",
        "effective_hours",
        "fallback_reason",
    ]
    records: list[dict[str, object]] = []
    for unit in units:
        if unit.endswith("_other"):
            continue
        selection = select_window(
            posts,
            unit,
            hours=hours,
            fallback_hours=fallback_hours,
            minimum=minimum,
        )
        rows = selection.rows
        sample_size = len(rows)
        totals = engagement_totals(rows)
        records.append(
            {
                "analysis_unit": unit,
                "job": labels.get(unit, unit),
                "sample_size": sample_size,
                "total_comments": totals["comments"],
                "comments_per_post": (totals["comments"] / sample_size if sample_size else 0.0),
                "total_recommendations": totals["recommendations"],
                "recommendations_per_post": (
                    totals["recommendations"] / sample_size if sample_size else 0.0
                ),
                "total_views": totals["views"],
                "views_per_post": totals["views"] / sample_size if sample_size else 0.0,
                "effective_hours": selection.effective_hours,
                "fallback_reason": selection.fallback_reason,
            }
        )
    return (
        pd.DataFrame.from_records(records, columns=columns)
        .sort_values(["comments_per_post", "sample_size", "job"], ascending=[False, False, True])
        .reset_index(drop=True)
    )


def collection_health(bundle: ExportBundle) -> CollectionHealth:
    runs = bundle.runs
    total = len(runs)
    succeeded = int((runs["status"] == "succeeded").sum()) if total else 0
    failed_mask = runs["status"].isin(["failed", "partial"]) if total else pd.Series(dtype=bool)
    failed = runs.loc[failed_mask].sort_values("scheduled_at_slot_kst", ascending=False).copy()
    latest_slot = bundle.posts["observed_at_slot_kst"].max() if not bundle.posts.empty else None
    return CollectionHealth(
        total_runs=total,
        succeeded_runs=succeeded,
        failed_runs=int((runs["status"] == "failed").sum()) if total else 0,
        partial_runs=int((runs["status"] == "partial").sum()) if total else 0,
        success_rate=succeeded / total if total else 0.0,
        latest_slot=pd.Timestamp(latest_slot) if latest_slot is not None else None,
        failed=failed,
    )
