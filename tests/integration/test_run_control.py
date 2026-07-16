from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from maple_monitor.ops.health import collector_is_healthy
from maple_monitor.ops.run_control import (
    collector_lock_key,
    release_collector_lock,
    try_collector_lock,
)


KST = ZoneInfo("Asia/Seoul")


def test_collector_lock_serializes_independent_database_connections(
    db_engine: Engine,
) -> None:
    slot = datetime(2026, 7, 15, 18, 20, tzinfo=KST)
    key = collector_lock_key("metadata:warrior", slot)

    with db_engine.connect() as first, db_engine.connect() as second:
        assert try_collector_lock(first, key) is True
        assert try_collector_lock(second, key) is False
        release_collector_lock(first, key)
        assert try_collector_lock(second, key) is True
        release_collector_lock(second, key)


def test_collector_health_requires_at_least_one_recent_successful_source(
    db_session: Session,
) -> None:
    now = datetime(2026, 7, 15, 18, 30, tzinfo=KST)
    db_session.execute(text("DELETE FROM run_slots WHERE job_type LIKE 'metadata:%'"))
    db_session.execute(text("DELETE FROM collection_runs WHERE job_type LIKE 'metadata:%'"))

    assert collector_is_healthy(db_session, now=now, max_age_hours=13) is False

    db_session.execute(
        text(
            "INSERT INTO collection_runs "
            "(id, job_type, scheduled_at_slot_kst, status, config_version, "
            "started_at, finished_at) VALUES "
            "(:id, 'metadata:warrior', :slot, 'partial', :config, :started, :finished)"
        ),
        {
            "id": uuid4(),
            "slot": now - timedelta(hours=6),
            "config": "a" * 64,
            "started": now - timedelta(hours=1, minutes=1),
            "finished": now - timedelta(hours=1),
        },
    )

    assert collector_is_healthy(db_session, now=now, max_age_hours=13) is False

    db_session.execute(
        text(
            "INSERT INTO collection_runs "
            "(id, job_type, scheduled_at_slot_kst, status, config_version, "
            "started_at, finished_at, diagnostics) VALUES "
            "(:id, 'metadata:magician', :slot, 'succeeded', :config, :started, :finished, "
            "'{\"accepted\": 1}'::jsonb)"
        ),
        {
            "id": uuid4(),
            "slot": now - timedelta(hours=6),
            "config": "b" * 64,
            "started": now - timedelta(minutes=31),
            "finished": now - timedelta(minutes=30),
        },
    )

    assert collector_is_healthy(db_session, now=now, max_age_hours=13) is True
