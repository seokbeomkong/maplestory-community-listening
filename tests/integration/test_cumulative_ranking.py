from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from threading import Event
from time import monotonic
from uuid import uuid4

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.orm import Session


AS_OF = datetime(2026, 7, 15, 6, tzinfo=UTC)
CONFIG_VERSION = "b" * 64


@dataclass(frozen=True)
class RankFixture:
    board_id: int
    as_of: datetime
    base_ids: tuple[int, ...]
    view_winner: int
    recommendation_winner: int
    comment_winner: int
    tie_low: int
    tie_high: int
    latest_snapshot_post: int
    cutoff_boundary: int
    released_quarantine: int
    excluded_ids: frozenset[int]
    other_unit_post: int | None


def _seed_rank_fixture(
    session: Session,
    *,
    board_id: int,
    first_post_id: int,
    as_of: datetime,
    include_preserved_rows: bool = True,
) -> RankFixture:
    session.execute(
        text("INSERT INTO boards (id, name, kind) VALUES (:board_id, 'rank', 'job')"),
        {"board_id": board_id},
    )
    base_ids = tuple(first_post_id + offset for offset in range(60))
    posts: list[dict[str, object]] = []
    snapshots: list[dict[str, object]] = []
    for offset, post_id in enumerate(base_ids):
        published_at = as_of - timedelta(days=offset % 30, minutes=offset)
        if offset in (3, 4):
            published_at = as_of - timedelta(days=3)
        posts.append(
            {
                "board_id": board_id,
                "post_id": post_id,
                "analysis_unit": "hero",
                "title": f"rank post {offset}",
                "published_at": published_at,
                "source_url": f"https://example.invalid/posts/{post_id}",
                "is_notice": False,
                "is_ad": False,
            }
        )
        views = 10_000 + offset
        recommendations = 20_000 + offset
        comments = 30_000 + offset
        if offset == 0:
            views = 1_000_000
        elif offset == 1:
            recommendations = 1_000_000
        elif offset == 2:
            comments = 1_000_000
        elif offset in (3, 4):
            views = recommendations = comments = 600_000
        elif offset == 5:
            views = recommendations = comments = 700_000
        snapshots.append(
            {
                "board_id": board_id,
                "post_id": post_id,
                "slot": as_of - timedelta(hours=2),
                "views": views,
                "recommendations": recommendations,
                "comments": comments,
                "config_version": CONFIG_VERSION,
            }
        )

    cutoff_boundary = first_post_id + 60
    released_quarantine = first_post_id + 61
    notice = first_post_id + 70
    ad = first_post_id + 71
    outside_window = first_post_id + 72
    future_published = first_post_id + 73
    active_quarantine = first_post_id + 74
    confirmed_quarantine = first_post_id + 75
    exceptional_posts = [
        (cutoff_boundary, "hero", as_of - timedelta(days=90), False, False, 750_000),
        (released_quarantine, "hero", as_of - timedelta(days=2), False, False, 740_000),
        (notice, "hero", as_of - timedelta(days=1), True, False, 2_000_000),
        (ad, "hero", as_of - timedelta(days=1), False, True, 2_000_000),
        (
            outside_window,
            "hero",
            as_of - timedelta(days=90, microseconds=1),
            False,
            False,
            2_000_000,
        ),
        (future_published, "hero", as_of + timedelta(seconds=1), False, False, 2_000_000),
        (active_quarantine, "hero", as_of - timedelta(days=1), False, False, 2_000_000),
        (confirmed_quarantine, "hero", as_of - timedelta(days=1), False, False, 2_000_000),
    ]
    for post_id, analysis_unit, published_at, is_notice, is_ad, metric_value in exceptional_posts:
        posts.append(
            {
                "board_id": board_id,
                "post_id": post_id,
                "analysis_unit": analysis_unit,
                "title": f"exception {post_id}",
                "published_at": published_at,
                "source_url": f"https://example.invalid/posts/{post_id}",
                "is_notice": is_notice,
                "is_ad": is_ad,
            }
        )
        snapshots.append(
            {
                "board_id": board_id,
                "post_id": post_id,
                "slot": as_of - timedelta(hours=1),
                "views": metric_value,
                "recommendations": metric_value,
                "comments": metric_value,
                "config_version": CONFIG_VERSION,
            }
        )

    other_unit_post: int | None = None
    if include_preserved_rows:
        other_unit_post = first_post_id + 80
        posts.append(
            {
                "board_id": board_id,
                "post_id": other_unit_post,
                "analysis_unit": "paladin",
                "title": "other unit",
                "published_at": as_of - timedelta(days=1),
                "source_url": f"https://example.invalid/posts/{other_unit_post}",
                "is_notice": False,
                "is_ad": False,
            }
        )

    session.execute(
        text(
            "INSERT INTO posts "
            "(board_id, post_id, analysis_unit, title, published_at, source_url, "
            "is_notice, is_ad) VALUES "
            "(:board_id, :post_id, :analysis_unit, :title, :published_at, :source_url, "
            ":is_notice, :is_ad)"
        ),
        posts,
    )
    session.execute(
        text(
            "INSERT INTO post_metric_snapshots "
            "(board_id, post_id, observed_at_slot_kst, views, recommendations, comments, "
            "config_version) VALUES "
            "(:board_id, :post_id, :slot, :views, :recommendations, :comments, "
            ":config_version)"
        ),
        snapshots,
    )
    session.execute(
        text(
            "INSERT INTO post_metric_snapshots "
            "(board_id, post_id, observed_at_slot_kst, views, recommendations, comments, "
            "config_version) VALUES "
            "(:board_id, :post_id, :slot, :value, :value, :value, :config_version)"
        ),
        [
            {
                "board_id": board_id,
                "post_id": base_ids[5],
                "slot": as_of - timedelta(hours=1),
                "value": 800_000,
                "config_version": CONFIG_VERSION,
            },
            {
                "board_id": board_id,
                "post_id": base_ids[5],
                "slot": as_of + timedelta(hours=1),
                "value": 900_000,
                "config_version": CONFIG_VERSION,
            },
        ],
    )
    for post_id, review_state in (
        (active_quarantine, "pending"),
        (confirmed_quarantine, "confirmed"),
        (released_quarantine, "released"),
    ):
        session.execute(
            text(
                "INSERT INTO security_quarantine "
                "(id, source_kind, source_ref, content_hash, findings, risk_score, "
                "review_state, reviewer, note, released_at) VALUES "
                "(:id, 'title', :source_ref, :content_hash, '[]'::jsonb, 90, "
                ":review_state, :reviewer, :note, :released_at)"
            ),
            {
                "id": uuid4(),
                "source_ref": f"post:{board_id}:{post_id}",
                "content_hash": f"{post_id:064x}"[-64:],
                "review_state": review_state,
                "reviewer": None if review_state == "pending" else "operator",
                "note": None if review_state == "pending" else "reviewed",
                "released_at": as_of if review_state == "released" else None,
            },
        )

    if include_preserved_rows:
        assert other_unit_post is not None
        session.execute(
            text(
                "INSERT INTO cumulative_top_posts "
                "(analysis_unit, metric, as_of_slot_kst, rank, board_id, post_id, "
                "metric_value, config_version) VALUES "
                "('hero', 'views', :other_slot, 1, :board_id, :hero_post, 1, :version), "
                "('paladin', 'views', :as_of, 1, :board_id, :other_post, 2, :version)"
            ),
            {
                "other_slot": as_of - timedelta(days=1),
                "as_of": as_of,
                "board_id": board_id,
                "hero_post": base_ids[-1],
                "other_post": other_unit_post,
                "version": "a" * 64,
            },
        )

    return RankFixture(
        board_id=board_id,
        as_of=as_of,
        base_ids=base_ids,
        view_winner=base_ids[0],
        recommendation_winner=base_ids[1],
        comment_winner=base_ids[2],
        tie_low=base_ids[3],
        tie_high=base_ids[4],
        latest_snapshot_post=base_ids[5],
        cutoff_boundary=cutoff_boundary,
        released_quarantine=released_quarantine,
        excluded_ids=frozenset(
            {notice, ad, outside_window, future_published, active_quarantine, confirmed_quarantine}
        ),
        other_unit_post=other_unit_post,
    )


def _seed_basic_rank_fixture(session: Session) -> None:
    session.execute(text("INSERT INTO boards (id, name, kind) VALUES (5501, 'rank', 'job')"))
    for offset in range(60):
        post_id = 5_500_000 + offset
        session.execute(
            text(
                "INSERT INTO posts "
                "(board_id, post_id, analysis_unit, title, published_at, source_url) "
                "VALUES (5501, :post_id, 'hero', :title, :published_at, :source_url)"
            ),
            {
                "post_id": post_id,
                "title": f"rank post {offset}",
                "published_at": AS_OF - timedelta(days=offset % 30),
                "source_url": f"https://example.invalid/posts/{post_id}",
            },
        )
        session.execute(
            text(
                "INSERT INTO post_metric_snapshots "
                "(board_id, post_id, observed_at_slot_kst, views, recommendations, comments, "
                "config_version) VALUES "
                "(5501, :post_id, :slot, :views, :recommendations, :comments, :config_version)"
            ),
            {
                "post_id": post_id,
                "slot": AS_OF - timedelta(hours=1),
                "views": 10_000 + offset,
                "recommendations": 1_000 + offset,
                "comments": 100 + offset,
                "config_version": CONFIG_VERSION,
            },
        )


def test_refresh_materializes_separate_top_fifty_per_metric(db_session: Session) -> None:
    from maple_monitor.ranking.cumulative import refresh_cumulative

    _seed_basic_rank_fixture(db_session)

    inserted = refresh_cumulative(
        db_session,
        AS_OF,
        window_days=90,
        top_n=50,
        config_version=CONFIG_VERSION,
    )

    assert inserted == 150
    assert db_session.execute(
        text(
            "SELECT metric, count(*), min(rank), max(rank) "
            "FROM cumulative_top_posts WHERE analysis_unit = 'hero' "
            "GROUP BY metric ORDER BY metric"
        )
    ).all() == [
        ("comments", 50, 1, 50),
        ("recommendations", 50, 1, 50),
        ("views", 50, 1, 50),
    ]


def test_refresh_enforces_window_quarantine_ordering_replay_and_safe_union(
    db_session: Session,
) -> None:
    from maple_monitor.ranking.cumulative import refresh_cumulative

    fixture = _seed_rank_fixture(
        db_session,
        board_id=5502,
        first_post_id=5_510_000,
        as_of=AS_OF,
    )

    inserted = refresh_cumulative(
        db_session,
        fixture.as_of,
        window_days=90,
        top_n=50,
        config_version=CONFIG_VERSION,
    )
    assert inserted == 150

    rows = db_session.execute(
        text(
            "SELECT metric, rank, post_id, metric_value, config_version "
            "FROM cumulative_top_posts "
            "WHERE analysis_unit = 'hero' AND as_of_slot_kst = :as_of "
            "ORDER BY metric, rank"
        ),
        {"as_of": fixture.as_of},
    ).all()
    by_metric = {
        metric: [row for row in rows if row.metric == metric]
        for metric in ("comments", "recommendations", "views")
    }
    assert {metric: len(metric_rows) for metric, metric_rows in by_metric.items()} == {
        "comments": 50,
        "recommendations": 50,
        "views": 50,
    }
    assert by_metric["views"][0].post_id == fixture.view_winner
    assert by_metric["recommendations"][0].post_id == fixture.recommendation_winner
    assert by_metric["comments"][0].post_id == fixture.comment_winner
    for metric_rows in by_metric.values():
        assert [row.rank for row in metric_rows] == list(range(1, 51))
        assert {row.config_version for row in metric_rows} == {CONFIG_VERSION}
        ranked_ids = [row.post_id for row in metric_rows]
        assert fixture.excluded_ids.isdisjoint(ranked_ids)
        assert fixture.cutoff_boundary in ranked_ids
        assert fixture.released_quarantine in ranked_ids
        assert ranked_ids.index(fixture.tie_high) < ranked_ids.index(fixture.tie_low)
        latest_row = next(row for row in metric_rows if row.post_id == fixture.latest_snapshot_post)
        assert latest_row.metric_value == 800_000

    union = db_session.execute(
        text(
            "SELECT board_id, post_id FROM cumulative_top_posts "
            "WHERE analysis_unit = 'hero' AND as_of_slot_kst = :as_of "
            "GROUP BY board_id, post_id ORDER BY board_id, post_id"
        ),
        {"as_of": fixture.as_of},
    ).all()
    work = db_session.execute(
        text(
            "SELECT task_key, payload, available_at, payload_hash, kind, state "
            "FROM work_items WHERE task_key LIKE :prefix ORDER BY task_key"
        ),
        {"prefix": f"detail:{fixture.board_id}:%"},
    ).all()
    assert 50 <= len(union) < 150
    assert len(work) == len(union)
    assert {row.task_key for row in work} == {
        f"detail:{board_id}:{post_id}:deep-v1" for board_id, post_id in union
    }
    assert all(set(row.payload) == {"board_id", "post_id"} for row in work)
    assert all(row.available_at == fixture.as_of for row in work)
    assert all(row.payload_hash is None for row in work)
    assert all((row.kind, row.state) == ("detail_fetch", "pending") for row in work)

    before_replay = [tuple(row) for row in rows]
    assert (
        refresh_cumulative(
            db_session,
            fixture.as_of,
            window_days=90,
            top_n=50,
            config_version=CONFIG_VERSION,
        )
        == 150
    )
    after_replay = db_session.execute(
        text(
            "SELECT metric, rank, post_id, metric_value, config_version "
            "FROM cumulative_top_posts "
            "WHERE analysis_unit = 'hero' AND as_of_slot_kst = :as_of "
            "ORDER BY metric, rank"
        ),
        {"as_of": fixture.as_of},
    ).all()
    assert [tuple(row) for row in after_replay] == before_replay
    assert db_session.execute(
        text("SELECT count(*) FROM work_items WHERE task_key LIKE :prefix"),
        {"prefix": f"detail:{fixture.board_id}:%"},
    ).scalar_one() == len(union)

    assert (
        db_session.execute(
            text(
                "SELECT count(*) FROM cumulative_top_posts "
                "WHERE analysis_unit = 'hero' AND as_of_slot_kst = :slot"
            ),
            {"slot": fixture.as_of - timedelta(days=1)},
        ).scalar_one()
        == 1
    )
    assert (
        db_session.execute(
            text(
                "SELECT post_id FROM cumulative_top_posts "
                "WHERE analysis_unit = 'paladin' AND as_of_slot_kst = :slot"
            ),
            {"slot": fixture.as_of},
        ).scalar_one()
        == fixture.other_unit_post
    )


@pytest.mark.parametrize(
    ("overrides", "error_type"),
    [
        ({"as_of_slot": datetime(2026, 7, 15, 6)}, ValueError),
        ({"as_of_slot": "2026-07-15"}, TypeError),
        (
            {"as_of_slot": datetime.min.replace(tzinfo=timezone(timedelta(hours=14)))},
            ValueError,
        ),
        ({"window_days": 0}, ValueError),
        ({"window_days": 366}, ValueError),
        ({"window_days": True}, TypeError),
        ({"top_n": 0}, ValueError),
        ({"top_n": 501}, ValueError),
        ({"top_n": True}, TypeError),
        ({"config_version": "A" * 64}, ValueError),
        ({"config_version": "a" * 63}, ValueError),
        ({"config_version": 1}, TypeError),
    ],
)
def test_refresh_rejects_invalid_inputs_before_database_work(
    db_session: Session,
    overrides: dict[str, object],
    error_type: type[Exception],
) -> None:
    from maple_monitor.ranking.cumulative import refresh_cumulative

    arguments: dict[str, object] = {
        "as_of_slot": AS_OF,
        "window_days": 90,
        "top_n": 50,
        "config_version": CONFIG_VERSION,
    }
    arguments.update(overrides)

    with pytest.raises(error_type):
        refresh_cumulative(db_session, **arguments)  # type: ignore[arg-type]


def _cleanup_rank_fixture(engine: Engine, board_id: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM work_items WHERE task_key LIKE :prefix"),
            {"prefix": f"detail:{board_id}:%"},
        )
        connection.execute(
            text("DELETE FROM cumulative_top_posts WHERE board_id = :board_id"),
            {"board_id": board_id},
        )
        connection.execute(
            text("DELETE FROM security_quarantine WHERE source_ref LIKE :prefix"),
            {"prefix": f"post:{board_id}:%"},
        )
        connection.execute(
            text("DELETE FROM post_metric_snapshots WHERE board_id = :board_id"),
            {"board_id": board_id},
        )
        connection.execute(
            text("DELETE FROM posts WHERE board_id = :board_id"),
            {"board_id": board_id},
        )
        connection.execute(
            text("DELETE FROM boards WHERE id = :board_id"),
            {"board_id": board_id},
        )


@contextmanager
def _persisted_rank_fixture(
    engine: Engine,
    *,
    board_id: int,
    first_post_id: int,
    as_of: datetime,
) -> Iterator[RankFixture]:
    with Session(engine) as setup_session:
        with setup_session.begin():
            if setup_session.execute(
                text("SELECT count(*) FROM boards WHERE id = :board_id"),
                {"board_id": board_id},
            ).scalar_one():
                raise RuntimeError(f"rank fixture board {board_id} already exists")
            fixture = _seed_rank_fixture(
                setup_session,
                board_id=board_id,
                first_post_id=first_post_id,
                as_of=as_of,
                include_preserved_rows=False,
            )

    try:
        yield fixture
    finally:
        _cleanup_rank_fixture(engine, board_id)


def test_caller_rollback_removes_rankings_and_new_detail_work(db_engine: Engine) -> None:
    from maple_monitor.ranking.cumulative import refresh_cumulative

    board_id = 5503
    as_of = AS_OF + timedelta(days=1)
    with _persisted_rank_fixture(
        db_engine,
        board_id=board_id,
        first_post_id=5_520_000,
        as_of=as_of,
    ) as fixture:
        with Session(db_engine) as session:
            assert (
                refresh_cumulative(
                    session,
                    fixture.as_of,
                    window_days=90,
                    top_n=50,
                    config_version=CONFIG_VERSION,
                )
                == 150
            )
            assert (
                session.execute(
                    text("SELECT count(*) FROM cumulative_top_posts WHERE board_id = :board_id"),
                    {"board_id": board_id},
                ).scalar_one()
                == 150
            )
            session.rollback()

        with db_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM cumulative_top_posts WHERE board_id = :board_id"),
                    {"board_id": board_id},
                ).scalar_one()
                == 0
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM work_items WHERE task_key LIKE :prefix"),
                    {"prefix": f"detail:{board_id}:%"},
                ).scalar_one()
                == 0
            )


def test_concurrent_refreshes_serialize_and_leave_one_stable_slot(db_engine: Engine) -> None:
    from maple_monitor.ranking.cumulative import refresh_cumulative

    board_id = 5504
    as_of = AS_OF + timedelta(days=2)
    first_refresh_complete = Event()
    allow_first_commit = Event()
    second_refresh_calling = Event()
    second_backend_pid: list[int] = []
    owns_fixture = False
    try:
        with Session(db_engine) as setup_session:
            with setup_session.begin():
                fixture = _seed_rank_fixture(
                    setup_session,
                    board_id=board_id,
                    first_post_id=5_530_000,
                    as_of=as_of,
                    include_preserved_rows=False,
                )
        owns_fixture = True

        def run_first_refresh() -> int:
            with Session(db_engine) as session:
                with session.begin():
                    inserted = refresh_cumulative(
                        session,
                        fixture.as_of,
                        window_days=90,
                        top_n=50,
                        config_version=CONFIG_VERSION,
                    )
                    first_refresh_complete.set()
                    if not allow_first_commit.wait(timeout=10):
                        raise TimeoutError("timed out waiting to release first refresh transaction")
                    return inserted

        def run_second_refresh() -> int:
            if not first_refresh_complete.wait(timeout=10):
                raise TimeoutError("first refresh did not acquire its transaction lock")
            with Session(db_engine) as session:
                with session.begin():
                    second_backend_pid.append(
                        session.execute(text("SELECT pg_backend_pid()")).scalar_one()
                    )
                    second_refresh_calling.set()
                    return refresh_cumulative(
                        session,
                        fixture.as_of,
                        window_days=90,
                        top_n=50,
                        config_version=CONFIG_VERSION,
                    )

        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(run_first_refresh)
            assert first_refresh_complete.wait(timeout=10)
            second_future = executor.submit(run_second_refresh)
            assert second_refresh_calling.wait(timeout=10)
            assert len(second_backend_pid) == 1
            deadline = monotonic() + 10
            second_is_waiting_for_advisory_lock = False
            try:
                while monotonic() < deadline:
                    with db_engine.connect() as connection:
                        second_is_waiting_for_advisory_lock = connection.execute(
                            text(
                                "SELECT EXISTS ("
                                "SELECT 1 FROM pg_locks "
                                "WHERE pid = :pid AND locktype = 'advisory' AND granted IS FALSE)"
                            ),
                            {"pid": second_backend_pid[0]},
                        ).scalar_one()
                    if second_is_waiting_for_advisory_lock:
                        break
                    allow_first_commit.wait(timeout=0.02)
                assert second_is_waiting_for_advisory_lock
                assert not second_future.done()
            finally:
                allow_first_commit.set()

            assert sorted([first_future.result(timeout=20), second_future.result(timeout=20)]) == [
                150,
                150,
            ]

        with db_engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM cumulative_top_posts "
                        "WHERE board_id = :board_id AND as_of_slot_kst = :as_of"
                    ),
                    {"board_id": board_id, "as_of": as_of},
                ).scalar_one()
                == 150
            )
            ranked_union = connection.execute(
                text(
                    "SELECT count(DISTINCT post_id) FROM cumulative_top_posts "
                    "WHERE board_id = :board_id AND as_of_slot_kst = :as_of"
                ),
                {"board_id": board_id, "as_of": as_of},
            ).scalar_one()
            assert (
                connection.execute(
                    text("SELECT count(*) FROM work_items WHERE task_key LIKE :prefix"),
                    {"prefix": f"detail:{board_id}:%"},
                ).scalar_one()
                == ranked_union
            )
    finally:
        allow_first_commit.set()
        if owns_fixture:
            _cleanup_rank_fixture(db_engine, board_id)


def test_persisted_fixture_refuses_to_delete_a_preexisting_sentinel_board(
    db_engine: Engine,
) -> None:
    board_id = 1_500_000_000 + (uuid4().int % 500_000_000)
    with db_engine.begin() as connection:
        while connection.execute(
            text("SELECT count(*) FROM boards WHERE id = :board_id"),
            {"board_id": board_id},
        ).scalar_one():
            board_id = 1_500_000_000 + (uuid4().int % 500_000_000)
        connection.execute(
            text(
                "INSERT INTO boards (id, name, kind) "
                "VALUES (:board_id, 'rank-fixture-sentinel', 'job')"
            ),
            {"board_id": board_id},
        )

    try:
        with pytest.raises(RuntimeError, match="already exists"):
            with _persisted_rank_fixture(
                db_engine,
                board_id=board_id,
                first_post_id=5_560_000,
                as_of=AS_OF + timedelta(days=3),
            ):
                raise AssertionError("preexisting board must prevent fixture ownership")

        with db_engine.connect() as connection:
            assert connection.execute(
                text("SELECT name, kind FROM boards WHERE id = :board_id"),
                {"board_id": board_id},
            ).one() == ("rank-fixture-sentinel", "job")
    finally:
        with db_engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM boards WHERE id = :board_id "
                    "AND name = 'rank-fixture-sentinel' "
                    "AND NOT EXISTS (SELECT 1 FROM posts WHERE board_id = :board_id)"
                ),
                {"board_id": board_id},
            )


def test_cumulative_table_catalog_contract(db_session: Session) -> None:
    inspector = inspect(db_session.bind)
    columns = {column["name"]: column for column in inspector.get_columns("cumulative_top_posts")}

    assert list(columns) == [
        "analysis_unit",
        "metric",
        "as_of_slot_kst",
        "rank",
        "board_id",
        "post_id",
        "metric_value",
        "config_version",
    ]
    assert all(not column["nullable"] for column in columns.values())
    assert inspector.get_pk_constraint("cumulative_top_posts") == {
        "name": "cumulative_top_posts_pkey",
        "constrained_columns": ["analysis_unit", "metric", "as_of_slot_kst", "post_id"],
        "comment": None,
        "dialect_options": {"postgresql_include": []},
    }
    unique = {
        item["name"]: item["column_names"]
        for item in inspector.get_unique_constraints("cumulative_top_posts")
    }
    assert unique["cumulative_top_posts_unit_metric_slot_rank_key"] == [
        "analysis_unit",
        "metric",
        "as_of_slot_kst",
        "rank",
    ]
    foreign_keys = inspector.get_foreign_keys("cumulative_top_posts")
    assert any(
        item["name"] == "cumulative_top_posts_post_fkey"
        and item["constrained_columns"] == ["board_id", "post_id"]
        and item["referred_table"] == "posts"
        and item["referred_columns"] == ["board_id", "post_id"]
        for item in foreign_keys
    )
    indexes = {item["name"]: item for item in inspector.get_indexes("cumulative_top_posts")}
    assert indexes["cumulative_latest_idx"]["column_names"] == [
        "analysis_unit",
        "metric",
        "as_of_slot_kst",
        "rank",
    ]
    constraint_names = set(
        db_session.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'cumulative_top_posts'::regclass"
            )
        ).scalars()
    )
    assert {
        "cumulative_top_posts_metric_check",
        "cumulative_top_posts_rank_check",
        "cumulative_top_posts_metric_value_check",
    } <= constraint_names


def test_load_cumulative_top_selects_latest_bounded_slot_with_stable_schema(
    db_session: Session,
) -> None:
    from maple_monitor.dashboard.queries import load_cumulative_top

    board_id = 5505
    post_id = 5_540_000
    older_slot = AS_OF - timedelta(hours=6)
    db_session.execute(
        text("INSERT INTO boards (id, name, kind) VALUES (:board_id, 'query', 'job')"),
        {"board_id": board_id},
    )
    db_session.execute(
        text(
            "INSERT INTO posts "
            "(board_id, post_id, analysis_unit, title, published_at, source_url) VALUES "
            "(:board_id, :post_id, 'hero', :title, :published_at, :source_url)"
        ),
        {
            "board_id": board_id,
            "post_id": post_id,
            "title": "<script>escaped by native renderer</script>",
            "published_at": AS_OF - timedelta(days=1),
            "source_url": f"https://example.invalid/posts/{post_id}",
        },
    )
    db_session.execute(
        text(
            "INSERT INTO cumulative_top_posts "
            "(analysis_unit, metric, as_of_slot_kst, rank, board_id, post_id, "
            "metric_value, config_version) VALUES "
            "('hero', 'views', :older_slot, 1, :board_id, :post_id, 100, :older_version), "
            "('hero', 'views', :latest_slot, 1, :board_id, :post_id, 200, :latest_version)"
        ),
        {
            "older_slot": older_slot,
            "latest_slot": AS_OF,
            "board_id": board_id,
            "post_id": post_id,
            "older_version": "a" * 64,
            "latest_version": CONFIG_VERSION,
        },
    )

    latest = load_cumulative_top(db_session.connection(), "hero", "views")
    bounded = load_cumulative_top(
        db_session.connection(),
        "hero",
        "views",
        AS_OF - timedelta(hours=1),
    )
    empty = load_cumulative_top(db_session.connection(), "hero", "comments")

    expected_columns = [
        "rank",
        "title",
        "metric_value",
        "published_at",
        "source_url",
        "as_of_slot_kst",
        "config_version",
    ]
    assert latest.columns.tolist() == expected_columns
    assert latest.to_dict("records") == [
        {
            "rank": 1,
            "title": "<script>escaped by native renderer</script>",
            "metric_value": 200,
            "published_at": AS_OF - timedelta(days=1),
            "source_url": f"https://example.invalid/posts/{post_id}",
            "as_of_slot_kst": AS_OF,
            "config_version": CONFIG_VERSION,
        }
    ]
    assert bounded.iloc[0]["metric_value"] == 100
    assert bounded.iloc[0]["as_of_slot_kst"] == older_slot
    assert empty.empty
    assert empty.columns.tolist() == expected_columns


def test_load_cumulative_top_hard_caps_the_dashboard_at_fifty(db_session: Session) -> None:
    from maple_monitor.dashboard.queries import load_cumulative_top

    board_id = 5506
    first_post_id = 5_550_000
    db_session.execute(
        text("INSERT INTO boards (id, name, kind) VALUES (:board_id, 'bounded-query', 'job')"),
        {"board_id": board_id},
    )
    posts = [
        {
            "board_id": board_id,
            "post_id": first_post_id + offset,
            "title": f"bounded post {offset}",
            "published_at": AS_OF - timedelta(minutes=offset),
            "source_url": f"https://example.invalid/posts/{first_post_id + offset}",
        }
        for offset in range(51)
    ]
    db_session.execute(
        text(
            "INSERT INTO posts "
            "(board_id, post_id, analysis_unit, title, published_at, source_url) VALUES "
            "(:board_id, :post_id, 'hero', :title, :published_at, :source_url)"
        ),
        posts,
    )
    db_session.execute(
        text(
            "INSERT INTO cumulative_top_posts "
            "(analysis_unit, metric, as_of_slot_kst, rank, board_id, post_id, "
            "metric_value, config_version) VALUES "
            "('hero', 'views', :as_of, :rank, :board_id, :post_id, :metric_value, :version)"
        ),
        [
            {
                "as_of": AS_OF,
                "rank": offset + 1,
                "board_id": board_id,
                "post_id": first_post_id + offset,
                "metric_value": 1_000 - offset,
                "version": CONFIG_VERSION,
            }
            for offset in range(51)
        ],
    )

    frame = load_cumulative_top(db_session.connection(), "hero", "views")

    assert frame["rank"].tolist() == list(range(1, 51))


@pytest.mark.parametrize(
    ("analysis_unit", "metric", "as_of_slot", "error_type"),
    [
        ("Hero", "views", None, ValueError),
        ("hero; DROP TABLE posts", "views", None, ValueError),
        ("h" * 65, "views", None, ValueError),
        ("hero", "likes", None, ValueError),
        ("hero", "views", datetime(2026, 7, 15, 6), ValueError),
        (1, "views", None, TypeError),
        ("hero", 1, None, TypeError),
        ("hero", "views", "2026-07-15", TypeError),
    ],
)
def test_load_cumulative_top_rejects_unbounded_or_untrusted_filters(
    db_session: Session,
    analysis_unit: object,
    metric: object,
    as_of_slot: object,
    error_type: type[Exception],
) -> None:
    from maple_monitor.dashboard.queries import load_cumulative_top

    with pytest.raises(error_type):
        load_cumulative_top(  # type: ignore[arg-type]
            db_session.connection(),
            analysis_unit,
            metric,
            as_of_slot,
        )
