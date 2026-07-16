from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from maple_monitor.ops.health import collector_is_healthy
from maple_monitor.ops.run_control import (
    claim_run_slot,
    collector_lock_key,
    finish_run,
    release_collector_lock,
    reserve_run_page,
    try_collector_lock,
)


KST = ZoneInfo("Asia/Seoul")


def test_backfill_page_reservations_survive_crash_reacquisition(
    db_engine: Engine,
) -> None:
    slot = datetime(2026, 7, 16, 12, 20, tzinfo=KST)
    job_type = "metadata-backfill"
    try:
        with Session(db_engine) as session:
            first = claim_run_slot(
                session,
                job_type=job_type,
                slot=slot,
                config_version="a" * 64,
                started_at=slot,
            )
            session.commit()

        with Session(db_engine) as session:
            assert reserve_run_page(session, run_id=first.run_id, page_budget=2) == 1
            session.commit()

        with Session(db_engine) as session:
            reacquired = claim_run_slot(
                session,
                job_type=job_type,
                slot=slot,
                config_version="a" * 64,
                started_at=slot + timedelta(minutes=1),
            )
            session.commit()

        assert reacquired.run_id == first.run_id
        assert reacquired.attempts == 2
        assert reacquired.pages_consumed == 1

        with Session(db_engine) as session:
            assert reserve_run_page(session, run_id=first.run_id, page_budget=2) == 2
            assert reserve_run_page(session, run_id=first.run_id, page_budget=2) is None
            finish_run(
                session,
                run_id=first.run_id,
                status="partial",
                finished_at=slot + timedelta(minutes=2),
                diagnostics={"attempts": 2, "pages_consumed": 2},
            )
            session.commit()

        with Session(db_engine) as session:
            persisted = session.execute(
                text(
                    "SELECT status, diagnostics->>'pages_consumed' AS pages_consumed "
                    "FROM collection_runs WHERE id = :run_id"
                ),
                {"run_id": first.run_id},
            ).one()
        assert persisted == ("partial", "2")
    finally:
        with db_engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM run_slots WHERE job_type = :job_type "
                    "AND scheduled_at_slot_kst = :slot"
                ),
                {"job_type": job_type, "slot": slot},
            )
            connection.execute(
                text(
                    "DELETE FROM collection_runs WHERE job_type = :job_type "
                    "AND scheduled_at_slot_kst = :slot"
                ),
                {"job_type": job_type, "slot": slot},
            )


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
