from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.orm import Session

from maple_monitor.collection.backfill import run_backfill_budget
from maple_monitor.collection.types import PostListItem
from maple_monitor.config import load_settings
from maple_monitor.models import SourceBackfillState
from maple_monitor.sources import SOURCES, source_for_board


KST = ZoneInfo("Asia/Seoul")
SLOT = datetime(2026, 7, 16, 6, 20, tzinfo=KST)


def _clear_backfill_state(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM source_backfill_states"))
        connection.execute(
            text(
                "DELETE FROM boards AS board "
                "WHERE board.id IN (2294, 2295, 2296, 2297, 2298, 5974, 2300, 2304) "
                "AND NOT EXISTS ("
                "SELECT 1 FROM posts AS post WHERE post.board_id = board.id"
                ")"
            )
        )


def _item(post_id: int, published_at: datetime) -> PostListItem:
    source = source_for_board(5974)
    return PostListItem(
        board_id=source.board_id,
        post_id=post_id,
        analysis_unit="free",
        category="free",
        title=f"post {post_id}",
        published_at=published_at,
        views=1,
        recommendations=0,
        comments=0,
        source_url=f"https://www.inven.co.kr/board/maple/{source.board_id}/{post_id}",
        is_notice=False,
        is_ad=False,
    )


def test_source_backfill_schema_has_bounded_state_contract(db_engine: Engine) -> None:
    inspector = inspect(db_engine)
    columns = {column["name"]: column for column in inspector.get_columns("source_backfill_states")}

    assert set(columns) == {
        "source_key",
        "next_page",
        "checkpoint_post_id",
        "complete",
        "updated_at",
    }
    assert columns["source_key"]["nullable"] is False
    assert columns["next_page"]["nullable"] is False
    assert columns["checkpoint_post_id"]["nullable"] is True
    assert columns["complete"]["default"] is not None
    assert columns["updated_at"]["default"] is not None
    assert inspector.get_pk_constraint("source_backfill_states")["constrained_columns"] == [
        "source_key"
    ]
    checks = {constraint["name"] for constraint in inspector.get_check_constraints(
        "source_backfill_states"
    )}
    assert checks == {
        "source_backfill_states_next_page_check",
        "source_backfill_states_source_key_check",
    }
    assert next(
        index
        for index in inspector.get_indexes("source_backfill_states")
        if index["name"] == "source_backfill_states_updated_at_idx"
    )["column_names"] == ["updated_at"]


def test_backfill_never_exceeds_global_budget_and_round_robins_sources(
    db_engine: Engine,
) -> None:
    _clear_backfill_state(db_engine)
    calls: list[tuple[int, int]] = []
    try:
        summary = run_backfill_budget(
            db_engine,
            SLOT,
            load_settings(Path("config/settings.yaml")),
            fetch_page=lambda board_id, page: calls.append((board_id, page)) or b"page",
            parse_page=lambda board_id, html, fetched_at: [],
            fetched_at=lambda: SLOT,
            wait_between_pages=lambda: None,
        )

        assert summary.pages_fetched == 40
        assert len(calls) == 40
        assert calls[:16] == [
            *((source.board_id, 2) for source in SOURCES),
            *((source.board_id, 3) for source in SOURCES),
        ]
    finally:
        _clear_backfill_state(db_engine)


def test_next_cycle_overlaps_each_sources_checkpoint_page(db_engine: Engine) -> None:
    _clear_backfill_state(db_engine)
    source = source_for_board(5974)
    first_calls: list[int] = []
    second_calls: list[int] = []
    loaded = load_settings(Path("config/settings.yaml"))
    try:
        first = run_backfill_budget(
            db_engine,
            SLOT,
            loaded,
            sources=(source,),
            page_budget=3,
            fetch_page=lambda board_id, page: first_calls.append(page) or b"page",
            parse_page=lambda board_id, html, fetched_at: [],
            fetched_at=lambda: SLOT,
            wait_between_pages=lambda: None,
        )
        second = run_backfill_budget(
            db_engine,
            SLOT + timedelta(hours=6),
            loaded,
            sources=(source,),
            page_budget=2,
            fetch_page=lambda board_id, page: second_calls.append(page) or b"page",
            parse_page=lambda board_id, html, fetched_at: [],
            fetched_at=lambda: SLOT + timedelta(hours=6),
            wait_between_pages=lambda: None,
        )

        assert first.pages_fetched == 3
        assert second.pages_fetched == 2
        assert first_calls == [2, 3, 4]
        assert second_calls == [4, 5]
    finally:
        _clear_backfill_state(db_engine)


def test_backfill_marks_complete_at_first_ordinary_row_older_than_window(
    db_engine: Engine,
) -> None:
    _clear_backfill_state(db_engine)
    source = source_for_board(5974)
    recent = _item(991001, SLOT - timedelta(days=89))
    old = _item(991002, SLOT - timedelta(days=91))
    try:
        summary = run_backfill_budget(
            db_engine,
            SLOT,
            load_settings(Path("config/settings.yaml")),
            sources=(source,),
            page_budget=40,
            fetch_page=lambda board_id, page: b"page",
            parse_page=lambda board_id, html, fetched_at: [recent, old],
            fetched_at=lambda: SLOT,
            wait_between_pages=lambda: None,
        )

        with Session(db_engine) as session:
            state = session.get(SourceBackfillState, source.key)
            persisted = session.execute(
                select(text("count(*)")).select_from(text("posts")).where(
                    text("board_id = 5974 AND post_id IN (991001, 991002)")
                )
            ).scalar_one()
        assert summary.pages_fetched == 1
        assert summary.accepted == 1
        assert state is not None and state.complete is True
        assert persisted == 1
    finally:
        with db_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM post_metric_snapshots WHERE board_id=5974 AND post_id IN (991001,991002)")
            )
            connection.execute(
                text("DELETE FROM posts WHERE board_id=5974 AND post_id IN (991001,991002)")
            )
        _clear_backfill_state(db_engine)


def test_failed_backfill_page_does_not_advance_persisted_state(db_engine: Engine) -> None:
    _clear_backfill_state(db_engine)
    source = source_for_board(5974)
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO source_backfill_states "
                "(source_key, next_page, checkpoint_post_id) VALUES ('free', 9, 991234)"
            )
        )
    try:
        summary = run_backfill_budget(
            db_engine,
            SLOT,
            load_settings(Path("config/settings.yaml")),
            sources=(source,),
            page_budget=1,
            fetch_page=lambda board_id, page: (_ for _ in ()).throw(OSError("upstream")),
            parse_page=lambda board_id, html, fetched_at: [],
            fetched_at=lambda: SLOT,
            wait_between_pages=lambda: None,
        )

        with Session(db_engine) as session:
            state = session.get(SourceBackfillState, source.key)
        assert summary.failed_sources == ("free",)
        assert state is not None
        assert (state.next_page, state.checkpoint_post_id, state.complete) == (9, 991234, False)
    finally:
        _clear_backfill_state(db_engine)
