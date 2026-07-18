from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pandas as pd

from maple_monitor.dashboard.export_analysis import (
    collection_health,
    engagement_totals,
    job_comparison,
    rank_posts,
    select_window,
    source_period,
)
from maple_monitor.dashboard.export_data import ExportBundle


def _posts() -> pd.DataFrame:
    as_of = pd.Timestamp("2026-07-17 00:20:00", tz="Asia/Seoul")
    rows: list[dict[str, object]] = []
    for index, days_ago in enumerate((1, 2, 8, 10, 12, 20), start=1):
        rows.append(
            {
                "board_id": 2294,
                "board_name": "전사",
                "post_id": index,
                "analysis_unit": "hero",
                "title": f"히어로 글 {index}",
                "published_at": as_of - timedelta(days=days_ago),
                "source_url": f"https://www.inven.co.kr/board/maple/2294/{index}",
                "current_category": "히어로",
                "observed_at_slot_kst": as_of,
                "observed_at_actual": as_of,
                "views": 100 * index,
                "recommendations": index,
                "comments": index * 2,
                "config_version": "abc",
            }
        )
    rows.append(
        {
            **rows[0],
            "board_id": 5974,
            "post_id": 99,
            "analysis_unit": "free",
            "title": "자유게시판 글",
            "published_at": as_of - timedelta(hours=2),
            "comments": 30,
        }
    )
    return pd.DataFrame(rows)


def _bundle() -> ExportBundle:
    runs = pd.DataFrame(
        [
            {
                "id": "one",
                "job_type": "metadata:free",
                "scheduled_at_slot_kst": pd.Timestamp("2026-07-17 00:20:00", tz="UTC"),
                "status": "succeeded",
                "config_version": "abc",
                "started_at": pd.Timestamp("2026-07-17 00:20:00", tz="UTC"),
                "finished_at": pd.Timestamp("2026-07-17 00:21:00", tz="UTC"),
                "diagnostics": "{}",
            },
            {
                "id": "two",
                "job_type": "metadata:warrior",
                "scheduled_at_slot_kst": pd.Timestamp("2026-07-16 18:20:00", tz="UTC"),
                "status": "failed",
                "config_version": "abc",
                "started_at": pd.Timestamp("2026-07-16 18:20:00", tz="UTC"),
                "finished_at": pd.Timestamp("2026-07-16 18:21:00", tz="UTC"),
                "diagnostics": '{"attempts": 3}',
            },
        ]
    )
    return ExportBundle(
        posts=_posts(),
        rankings=pd.DataFrame(),
        runs=runs,
        quarantine=pd.DataFrame(),
        checksums={"latest_post_metrics.csv": True},
        source_path=Path("production.zip"),
    )


def test_job_window_falls_back_to_thirty_days_when_seven_days_is_sparse() -> None:
    result = select_window(_posts(), "hero", hours=168, fallback_hours=720, minimum=5)

    assert result.effective_hours == 720
    assert result.fallback_reason == "7일 표본 부족"
    assert len(result.rows) == 6


def test_free_window_keeps_twenty_four_hour_scope() -> None:
    result = select_window(_posts(), "free", hours=24)

    assert result.effective_hours == 24
    assert result.fallback_reason is None
    assert result.rows["title"].tolist() == ["자유게시판 글"]


def test_rank_posts_uses_one_factual_metric_and_stable_ties() -> None:
    rows = _posts().query("analysis_unit == 'hero'")

    ranked = rank_posts(rows, "comments", limit=3)

    assert ranked.columns.tolist() == [
        "title",
        "comments",
        "recommendations",
        "views",
        "published_at",
        "source_url",
    ]
    assert ranked["comments"].tolist() == [12, 10, 8]


def test_job_comparison_shows_sample_and_per_post_rates() -> None:
    comparison = job_comparison(_posts(), minimum=1)

    hero = comparison.query("analysis_unit == 'hero'").iloc[0]
    assert hero["sample_size"] == 2
    assert hero["total_comments"] == 6
    assert hero["comments_per_post"] == 3.0
    assert hero["total_views"] == 300
    assert hero["views_per_post"] == 150.0
    assert hero["analysis_period"] == "2026.07.10–2026.07.17"
    assert "free" not in comparison["analysis_unit"].tolist()


def test_engagement_totals_keep_each_counter_separate() -> None:
    totals = engagement_totals(_posts().query("analysis_unit == 'hero'"))

    assert totals == {
        "posts": 6,
        "comments": 42,
        "recommendations": 21,
        "views": 2100,
    }


def test_collection_health_keeps_failure_attributable() -> None:
    health = collection_health(_bundle())

    assert health.total_runs == 2
    assert health.succeeded_runs == 1
    assert health.failed_runs == 1
    assert health.failed.iloc[0]["job_type"] == "metadata:warrior"


def test_job_comparison_returns_a_typed_empty_projection() -> None:
    result = job_comparison(_posts().iloc[0:0])

    assert result.empty
    assert "analysis_period" in result.columns
    assert "effective_hours" in result.columns
    assert "fallback_reason" in result.columns


def test_collection_health_counts_partial_runs_separately() -> None:
    bundle = _bundle()
    partial = bundle.runs.iloc[[0]].assign(id="three", status="partial")
    runs = pd.concat([bundle.runs, partial], ignore_index=True)
    bundle = ExportBundle(
        posts=bundle.posts,
        rankings=bundle.rankings,
        runs=runs,
        quarantine=bundle.quarantine,
        checksums=bundle.checksums,
        source_path=bundle.source_path,
    )

    health = collection_health(bundle)

    assert health.failed_runs == 1
    assert health.partial_runs == 1
    assert len(health.failed) == 2


def test_source_period_uses_actual_filtered_publication_dates() -> None:
    rows = pd.DataFrame(
        {
            "published_at": pd.to_datetime(
                ["2026-04-17T01:00:00+09:00", "2026-07-17T23:00:00+09:00"], utc=True
            )
        }
    )

    period = source_period(rows)

    assert period.label == "2026.04.17–2026.07.17 게시물"
