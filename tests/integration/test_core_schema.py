from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


CORE_TABLES = {
    "boards",
    "posts",
    "post_metric_snapshots",
    "post_metric_snapshots_default",
    "collection_runs",
    "run_slots",
    "work_items",
}


def test_core_table_identities_and_default_partition_exist(db_engine: Engine) -> None:
    table_names = set(inspect(db_engine).get_table_names())

    assert CORE_TABLES <= table_names
    with db_engine.connect() as connection:
        partition_bound = connection.execute(
            text(
                "SELECT pg_get_expr(child.relpartbound, child.oid) "
                "FROM pg_class AS child "
                "JOIN pg_namespace AS namespace ON namespace.oid = child.relnamespace "
                "WHERE namespace.nspname = current_schema() "
                "AND child.relname = 'post_metric_snapshots_default'"
            )
        ).scalar_one()
    assert partition_bound == "DEFAULT"


def test_snapshot_slot_is_idempotent(db_session: Session) -> None:
    db_session.execute(text("INSERT INTO boards (id, name, kind) VALUES (2294, '전사', 'job')"))
    db_session.execute(
        text(
            "INSERT INTO posts "
            "(board_id, post_id, analysis_unit, title, published_at, source_url) "
            "VALUES (2294, 457159, 'hero', '제목', now(), "
            "'https://example.invalid/457159')"
        )
    )
    statement = text(
        "INSERT INTO post_metric_snapshots "
        "(board_id, post_id, observed_at_slot_kst, views, recommendations, comments, "
        "config_version) "
        "VALUES (2294, 457159, '2026-07-14T06:20:00+09:00', 100, 2, 3, repeat('a', 64))"
    )
    db_session.execute(statement)
    db_session.commit()

    with pytest.raises(IntegrityError):
        db_session.execute(statement)
        db_session.commit()


def test_work_item_key_is_unique(db_session: Session) -> None:
    values = {
        "key": "detail:2294:457159:v1",
        "kind": "detail_fetch",
        "available_at": datetime.now(UTC),
    }
    statement = text(
        "INSERT INTO work_items (task_key, kind, state, available_at) "
        "VALUES (:key, :kind, 'pending', :available_at)"
    )
    db_session.execute(statement, values)
    db_session.commit()

    with pytest.raises(IntegrityError):
        db_session.execute(statement, values)
        db_session.commit()


@pytest.mark.parametrize("kind", ["", "general", "JOB"])
def test_board_kind_is_constrained(db_session: Session, kind: str) -> None:
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("INSERT INTO boards (id, name, kind) VALUES (999, 'invalid', :kind)"),
            {"kind": kind},
        )
        db_session.commit()


@pytest.mark.parametrize("status", ["pending", "complete"])
def test_collection_run_status_is_constrained(db_session: Session, status: str) -> None:
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO collection_runs "
                "(id, job_type, scheduled_at_slot_kst, status, config_version, started_at) "
                "VALUES (:id, 'metadata', now(), :status, repeat('a', 64), now())"
            ),
            {"id": uuid4(), "status": status},
        )
        db_session.commit()


@pytest.mark.parametrize("state", ["running", "complete"])
def test_work_item_state_is_constrained(db_session: Session, state: str) -> None:
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO work_items (task_key, kind, state, available_at) "
                "VALUES (:key, 'detail_fetch', :state, now())"
            ),
            {"key": f"invalid:{state}", "state": state},
        )
        db_session.commit()


@pytest.mark.parametrize(
    ("column", "values"),
    [
        ("views", (-1, 0, 0)),
        ("recommendations", (0, -1, 0)),
        ("comments", (0, 0, -1)),
    ],
)
def test_snapshot_metrics_cannot_be_negative(
    db_session: Session, column: str, values: tuple[int, int, int]
) -> None:
    db_session.execute(text("INSERT INTO boards (id, name, kind) VALUES (2294, '전사', 'job')"))
    db_session.execute(
        text(
            "INSERT INTO posts "
            "(board_id, post_id, analysis_unit, title, published_at, source_url) "
            "VALUES (2294, 457159, 'hero', '제목', now(), "
            "'https://example.invalid/457159')"
        )
    )

    with pytest.raises(IntegrityError, match=column):
        db_session.execute(
            text(
                "INSERT INTO post_metric_snapshots "
                "(board_id, post_id, observed_at_slot_kst, views, recommendations, comments, "
                "config_version) VALUES "
                "(2294, 457159, now(), :views, :recommendations, :comments, repeat('a', 64))"
            ),
            dict(zip(("views", "recommendations", "comments"), values, strict=True)),
        )
        db_session.commit()


def test_work_item_defaults_and_claim_index(db_session: Session) -> None:
    row = db_session.execute(
        text(
            "INSERT INTO work_items (task_key, kind, state, available_at) "
            "VALUES ('defaults:v1', 'detail_fetch', 'pending', now()) "
            "RETURNING priority, payload, attempts, created_at, updated_at"
        )
    ).one()

    assert row.priority == 100
    assert row.payload == {}
    assert row.attempts == 0
    assert row.created_at is not None
    assert row.updated_at is not None
    index = next(
        item
        for item in inspect(db_session.bind).get_indexes("work_items")
        if item["name"] == "work_items_claim_idx"
    )
    assert index["column_names"] == ["state", "priority", "available_at", "id"]


def test_migration_upgrade_downgrade_upgrade_round_trip(database_url: str) -> None:
    source_url = make_url(database_url)
    database_name = f"maple_monitor_roundtrip_{uuid4().hex}"
    admin_engine = create_engine(source_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    target_url = source_url.set(database=database_name)
    config = Config("alembic.ini")

    try:
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        os.environ["DATABASE_URL"] = target_url.render_as_string(hide_password=False)

        command.upgrade(config, "head")
        target_engine = create_engine(target_url)
        try:
            assert CORE_TABLES <= set(inspect(target_engine).get_table_names())
        finally:
            target_engine.dispose()

        command.downgrade(config, "base")
        target_engine = create_engine(target_url)
        try:
            assert CORE_TABLES.isdisjoint(inspect(target_engine).get_table_names())
        finally:
            target_engine.dispose()

        command.upgrade(config, "head")
        target_engine = create_engine(target_url)
        try:
            assert CORE_TABLES <= set(inspect(target_engine).get_table_names())
        finally:
            target_engine.dispose()
    finally:
        os.environ["DATABASE_URL"] = database_url
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
        admin_engine.dispose()


def test_create_engine_from_env_connects_to_configured_database(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maple_monitor.db import create_engine_from_env

    monkeypatch.setenv("DATABASE_URL", database_url)
    engine = create_engine_from_env()
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT current_database()")).scalar_one()
                == make_url(database_url).database
            )
        assert engine.pool.size() == 3
    finally:
        engine.dispose()


def test_create_engine_from_env_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from maple_monitor.db import create_engine_from_env

    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(KeyError, match="DATABASE_URL"):
        create_engine_from_env()


def test_session_scope_commits_on_success(db_engine: Engine) -> None:
    from maple_monitor.db import session_scope

    board_id = 2_147_483_000
    with db_engine.begin() as connection:
        connection.execute(text("DELETE FROM boards WHERE id = :id"), {"id": board_id})
    try:
        with session_scope(db_engine) as session:
            session.execute(
                text("INSERT INTO boards (id, name, kind) VALUES (:id, 'commit', 'free')"),
                {"id": board_id},
            )

        with db_engine.connect() as connection:
            count = connection.execute(
                text("SELECT count(*) FROM boards WHERE id = :id"), {"id": board_id}
            ).scalar_one()
        assert count == 1
    finally:
        with db_engine.begin() as connection:
            connection.execute(text("DELETE FROM boards WHERE id = :id"), {"id": board_id})


def test_session_scope_rolls_back_on_error(db_engine: Engine) -> None:
    from maple_monitor.db import session_scope

    board_id = 2_147_483_001
    with db_engine.begin() as connection:
        connection.execute(text("DELETE FROM boards WHERE id = :id"), {"id": board_id})

    with pytest.raises(RuntimeError, match="force rollback"):
        with session_scope(db_engine) as session:
            session.execute(
                text("INSERT INTO boards (id, name, kind) VALUES (:id, 'rollback', 'free')"),
                {"id": board_id},
            )
            raise RuntimeError("force rollback")

    with db_engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM boards WHERE id = :id"), {"id": board_id}
        ).scalar_one()
    assert count == 0


def test_database_health_reports_ok_for_reachable_database(db_engine: Engine) -> None:
    from maple_monitor.ops.health import database_health

    assert database_health(db_engine) == {"database": "ok"}


def test_health_command_prints_success_json(database_url: str) -> None:
    import json

    from typer.testing import CliRunner

    from maple_monitor.cli import app

    result = CliRunner().invoke(app, ["health"], env={"DATABASE_URL": database_url})

    assert result.exit_code == 0, str(result.exception)
    assert json.loads(result.stdout) == {"database": "ok"}


def test_health_command_returns_nonzero_json_when_database_is_unreachable() -> None:
    import json

    from typer.testing import CliRunner

    from maple_monitor.cli import app

    unreachable_url = (
        "postgresql+psycopg://maple_monitor:maple_monitor@127.0.0.1:1/"
        "maple_monitor_test?connect_timeout=1"
    )
    result = CliRunner().invoke(app, ["health"], env={"DATABASE_URL": unreachable_url})

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {"database": "error"}


def test_orm_metadata_describes_core_tables_and_snapshot_partition() -> None:
    from maple_monitor.models import Base, PostMetricSnapshot

    assert set(Base.metadata.tables) == CORE_TABLES - {"post_metric_snapshots_default"}
    assert (
        PostMetricSnapshot.__table__.dialect_options["postgresql"]["partition_by"]
        == "RANGE (observed_at_slot_kst)"
    )


def test_alembic_metadata_does_not_treat_runtime_partitions_as_schema_drift() -> None:
    command.check(Config("alembic.ini"))
