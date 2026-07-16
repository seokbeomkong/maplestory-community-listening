from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session


RunDisposition = Literal["acquired", "already_succeeded"]


@dataclass(frozen=True)
class RunClaim:
    run_id: UUID
    disposition: RunDisposition
    attempts: int
    ranking_rows: int
    pages_consumed: int = 0


def _diagnostic_count(diagnostics: dict[str, object], key: str) -> int:
    value = diagnostics.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def collector_lock_key(job_type: str, slot: datetime) -> int:
    if not job_type or not isinstance(job_type, str):
        raise ValueError("job_type must be a non-empty string")
    if not isinstance(slot, datetime) or slot.tzinfo is None or slot.utcoffset() is None:
        raise ValueError("slot must be timezone-aware")
    identity = f"{job_type}:{slot.astimezone(UTC).isoformat()}".encode()
    return int.from_bytes(hashlib.sha256(identity).digest()[:8], byteorder="big", signed=True)


def try_collector_lock(connection: Connection, key: int) -> bool:
    return bool(
        connection.execute(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": key},
        ).scalar_one()
    )


def release_collector_lock(connection: Connection, key: int) -> None:
    connection.execute(
        text("SELECT pg_advisory_unlock(:lock_key)"),
        {"lock_key": key},
    )


def claim_run_slot(
    session: Session,
    *,
    job_type: str,
    slot: datetime,
    config_version: str,
    started_at: datetime,
) -> RunClaim:
    row = (
        session.execute(
            text(
                "SELECT run.id, run.status, run.diagnostics "
                "FROM run_slots AS slot "
                "JOIN collection_runs AS run ON run.id = slot.run_id "
                "WHERE slot.job_type = :job_type "
                "AND slot.scheduled_at_slot_kst = :scheduled_at"
            ),
            {"job_type": job_type, "scheduled_at": slot},
        )
        .mappings()
        .one_or_none()
    )

    if row is None:
        run_id = uuid4()
        attempts = 1
        diagnostics = {"attempts": attempts}
        session.execute(
            text(
                "INSERT INTO collection_runs "
                "(id, job_type, scheduled_at_slot_kst, status, config_version, "
                "started_at, diagnostics) VALUES "
                "(:id, :job_type, :scheduled_at, 'running', :config_version, "
                ":started_at, CAST(:diagnostics AS jsonb))"
            ),
            {
                "id": run_id,
                "job_type": job_type,
                "scheduled_at": slot,
                "config_version": config_version,
                "started_at": started_at,
                "diagnostics": json.dumps(diagnostics),
            },
        )
        session.execute(
            text(
                "INSERT INTO run_slots (job_type, scheduled_at_slot_kst, run_id) "
                "VALUES (:job_type, :scheduled_at, :run_id)"
            ),
            {"job_type": job_type, "scheduled_at": slot, "run_id": run_id},
        )
        return RunClaim(run_id, "acquired", attempts, 0)

    diagnostics = row["diagnostics"] if isinstance(row["diagnostics"], dict) else {}
    attempts = _diagnostic_count(diagnostics, "attempts")
    ranking_rows = _diagnostic_count(diagnostics, "ranking_rows")
    pages_consumed = _diagnostic_count(diagnostics, "pages_consumed")
    if row["status"] == "succeeded":
        return RunClaim(
            row["id"],
            "already_succeeded",
            attempts,
            ranking_rows,
            pages_consumed,
        )

    attempts += 1
    diagnostics["attempts"] = attempts
    session.execute(
        text(
            "UPDATE collection_runs SET status = 'running', config_version = :config_version, "
            "started_at = :started_at, finished_at = NULL, "
            "diagnostics = CAST(:diagnostics AS jsonb) WHERE id = :run_id"
        ),
        {
            "run_id": row["id"],
            "config_version": config_version,
            "started_at": started_at,
            "diagnostics": json.dumps(diagnostics, sort_keys=True),
        },
    )
    return RunClaim(row["id"], "acquired", attempts, ranking_rows, pages_consumed)


def reserve_run_page(
    session: Session,
    *,
    run_id: UUID,
    page_budget: int,
) -> int | None:
    """Atomically consume one durable page allowance for a running collection run."""

    if isinstance(page_budget, bool) or not isinstance(page_budget, int):
        raise TypeError("page_budget must be an integer")
    if page_budget < 0:
        raise ValueError("page_budget must be nonnegative")
    return session.execute(
        text(
            "UPDATE collection_runs SET diagnostics = jsonb_set("
            "COALESCE(diagnostics, '{}'::jsonb), '{pages_consumed}', "
            "to_jsonb(COALESCE((diagnostics->>'pages_consumed')::integer, 0) + 1), true) "
            "WHERE id = :run_id AND status = 'running' "
            "AND COALESCE((diagnostics->>'pages_consumed')::integer, 0) < :page_budget "
            "RETURNING (diagnostics->>'pages_consumed')::integer"
        ),
        {"run_id": run_id, "page_budget": page_budget},
    ).scalar_one_or_none()


def finish_run(
    session: Session,
    *,
    run_id: UUID,
    status: Literal["succeeded", "partial", "failed"],
    finished_at: datetime,
    diagnostics: dict[str, object],
) -> None:
    session.execute(
        text(
            "UPDATE collection_runs SET status = :status, finished_at = :finished_at, "
            "diagnostics = CAST(:diagnostics AS jsonb) WHERE id = :run_id"
        ),
        {
            "run_id": run_id,
            "status": status,
            "finished_at": finished_at,
            "diagnostics": json.dumps(diagnostics, sort_keys=True),
        },
    )


def collector_is_healthy(session: Session, *, now: datetime, max_age_hours: int) -> bool:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if isinstance(max_age_hours, bool) or not isinstance(max_age_hours, int):
        raise TypeError("max_age_hours must be an integer")
    if not 1 <= max_age_hours <= 168:
        raise ValueError("max_age_hours must be between 1 and 168")
    cutoff = now.astimezone(UTC) - timedelta(hours=max_age_hours)
    return bool(
        session.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM collection_runs "
                "WHERE job_type = 'hero_metadata' AND status = 'succeeded' "
                "AND finished_at >= :cutoff)"
            ),
            {"cutoff": cutoff},
        ).scalar_one()
    )
