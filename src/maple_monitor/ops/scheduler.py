from __future__ import annotations

import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, Literal
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from maple_monitor.collection.backfill import BackfillBudgetSummary, run_backfill_budget
from maple_monitor.collection.client import ListPageClientError, fetch_list_page
from maple_monitor.collection.pagination import scan_incremental_pages
from maple_monitor.collection.parser import InvalidSourcePage, parse_list_page
from maple_monitor.collection.repository import (
    SnapshotConfigConflict,
    highest_ordinary_post_id,
)
from maple_monitor.collection.service import align_kst_slot, collect_board_slot
from maple_monitor.config import LoadedSettings, load_settings
from maple_monitor.db import create_engine_from_env, session_scope
from maple_monitor.ops.health import collector_is_healthy
from maple_monitor.ops.run_control import (
    claim_run_slot,
    collector_lock_key,
    finish_run,
    release_collector_lock,
    reserve_run_page,
    try_collector_lock,
)
from maple_monitor.ranking.cumulative import refresh_cumulative
from maple_monitor.sources import SOURCES, SourceDefinition


KST: Final = ZoneInfo("Asia/Seoul")
_RETRYABLE_ERRORS: Final = (
    InvalidSourcePage,
    ListPageClientError,
    OSError,
    SQLAlchemyError,
    SnapshotConfigConflict,
)
_BACKFILL_JOB_TYPE: Final = "metadata-backfill"


@dataclass(frozen=True)
class SourceCycleResult:
    source_key: str
    status: Literal["succeeded", "partial", "failed", "busy", "already_succeeded"]
    pages_fetched: int
    accepted: int
    boundary_reached: bool


@dataclass(frozen=True)
class CollectionCycleSummary:
    slot: datetime
    sources: tuple[SourceCycleResult, ...]
    ranking_rows: int
    status: Literal["succeeded", "partial", "failed"]


def current_kst_time() -> datetime:
    return datetime.now(KST)


def dispose_engine(engine: Engine) -> None:
    engine.dispose()


def schedule_hours(interval_hours: int) -> str:
    if isinstance(interval_hours, bool) or not isinstance(interval_hours, int):
        raise TypeError("interval_hours must be an integer")
    if interval_hours < 1 or interval_hours > 24 or 24 % interval_hours:
        raise ValueError("interval_hours must divide 24")
    return ",".join(str(hour) for hour in range(0, 24, interval_hours))


def _wait_for_request(loaded: LoadedSettings) -> None:
    collection = loaded.settings.collection
    time.sleep(
        random.uniform(
            collection.request_min_delay_seconds,
            collection.request_max_delay_seconds,
        )
    )


def _finish_failed_source(
    engine: Engine,
    run_id: object | None,
    attempts: int,
) -> None:
    if run_id is None:
        return
    try:
        with session_scope(engine) as session:
            finish_run(
                session,
                run_id=run_id,
                status="failed",
                finished_at=current_kst_time(),
                diagnostics={"attempts": attempts, "error": "collection_failed"},
            )
    except SQLAlchemyError:
        pass


def _collect_source(
    engine: Engine,
    source: SourceDefinition,
    slot: datetime,
    started_at: datetime,
    loaded: LoadedSettings,
) -> SourceCycleResult:
    job_type = f"metadata:{source.key}"
    lock_key = collector_lock_key(job_type, slot)
    lock_connection = engine.connect()
    lock_acquired = False
    run_id: object | None = None
    attempts = 0
    try:
        lock_acquired = try_collector_lock(lock_connection, lock_key)
        if not lock_acquired:
            return SourceCycleResult(source.key, "busy", 0, 0, False)

        with session_scope(engine) as session:
            claim = claim_run_slot(
                session,
                job_type=job_type,
                slot=slot,
                config_version=loaded.config_version,
                started_at=started_at,
            )
        run_id = claim.run_id
        attempts = claim.attempts
        if claim.disposition == "already_succeeded":
            return SourceCycleResult(source.key, "already_succeeded", 0, 0, True)

        with session_scope(engine) as session:
            prior_high_water = highest_ordinary_post_id(session, source.board_id)
        scan = scan_incremental_pages(
            source,
            prior_high_water,
            loaded.settings.collection,
            fetch_page=fetch_list_page,
            parse_page=parse_list_page,
            fetched_at=current_kst_time,
            wait_between_pages=lambda: _wait_for_request(loaded),
        )
        if scan.status == "partial":
            with session_scope(engine) as session:
                finish_run(
                    session,
                    run_id=run_id,
                    status="partial",
                    finished_at=current_kst_time(),
                    diagnostics={
                        "attempts": attempts,
                        "pages_fetched": scan.pages_fetched,
                        "accepted": 0,
                        "boundary_reached": False,
                    },
                )
            return SourceCycleResult(source.key, "partial", scan.pages_fetched, 0, False)

        actual = current_kst_time()
        with session_scope(engine) as session:
            collection = collect_board_slot(
                session,
                source.board_id,
                scan.items,
                slot,
                loaded,
                fetched_at=actual,
            )
            accepted = collection.inserted + collection.updated
            finish_run(
                session,
                run_id=run_id,
                status="succeeded",
                finished_at=current_kst_time(),
                diagnostics={
                    "attempts": attempts,
                    "pages_fetched": scan.pages_fetched,
                    "accepted": accepted,
                    "boundary_reached": scan.boundary_reached,
                },
            )
        return SourceCycleResult(
            source.key,
            "succeeded",
            scan.pages_fetched,
            accepted,
            scan.boundary_reached,
        )
    except _RETRYABLE_ERRORS:
        _finish_failed_source(engine, run_id, attempts)
        return SourceCycleResult(source.key, "failed", 0, 0, False)
    finally:
        if lock_acquired:
            try:
                release_collector_lock(lock_connection, lock_key)
            except SQLAlchemyError:
                pass
        lock_connection.close()


def _cycle_status(
    results: tuple[SourceCycleResult, ...],
    *,
    backfill_failed: bool,
) -> Literal["succeeded", "partial", "failed"]:
    successful = sum(
        result.status in {"succeeded", "already_succeeded"} for result in results
    )
    if successful == len(results) and not backfill_failed:
        return "succeeded"
    if successful:
        return "partial"
    return "failed"


def _run_backfill_cycle(
    engine: Engine,
    slot: datetime,
    started_at: datetime,
    loaded: LoadedSettings,
    sources: tuple[SourceDefinition, ...],
) -> BackfillBudgetSummary:
    """Spend the slot's durable backfill allowance under one advisory lock."""

    lock_key = collector_lock_key(_BACKFILL_JOB_TYPE, slot)
    lock_connection = engine.connect()
    lock_acquired = False
    try:
        lock_acquired = try_collector_lock(lock_connection, lock_key)
        if not lock_acquired:
            return BackfillBudgetSummary(0, 0, (_BACKFILL_JOB_TYPE,))

        with session_scope(engine) as session:
            claim = claim_run_slot(
                session,
                job_type=_BACKFILL_JOB_TYPE,
                slot=slot,
                config_version=loaded.config_version,
                started_at=started_at,
            )
        if claim.disposition == "already_succeeded":
            return BackfillBudgetSummary(
                claim.pages_consumed,
                claim.accepted,
                claim.failed_sources,
            )

        page_budget = loaded.settings.collection.backfill_page_budget_per_cycle
        pages_consumed = claim.pages_consumed

        def reserve_page() -> bool:
            nonlocal pages_consumed
            with session_scope(engine) as session:
                reserved = reserve_run_page(
                    session,
                    run_id=claim.run_id,
                    page_budget=page_budget,
                )
            if reserved is None:
                return False
            pages_consumed = reserved
            return True

        try:
            summary = run_backfill_budget(
                engine,
                slot,
                loaded,
                fetch_page=fetch_list_page,
                parse_page=parse_list_page,
                fetched_at=current_kst_time,
                wait_between_pages=lambda: _wait_for_request(loaded),
                reserve_page=reserve_page,
                sources=sources,
            )
        except _RETRYABLE_ERRORS:
            with session_scope(engine) as session:
                finish_run(
                    session,
                    run_id=claim.run_id,
                    status="failed",
                    finished_at=current_kst_time(),
                    diagnostics={
                        "attempts": claim.attempts,
                        "pages_consumed": pages_consumed,
                        "error": "backfill_failed",
                    },
                )
            raise

        with session_scope(engine) as session:
            finish_run(
                session,
                run_id=claim.run_id,
                status="succeeded",
                finished_at=current_kst_time(),
                diagnostics={
                    "attempts": claim.attempts,
                    "pages_consumed": pages_consumed,
                    "accepted": summary.accepted,
                    "failed_sources": list(summary.failed_sources),
                },
            )
        return summary
    finally:
        if lock_acquired:
            try:
                release_collector_lock(lock_connection, lock_key)
            except SQLAlchemyError:
                pass
        lock_connection.close()


def collect_and_rank_once(settings_path: Path) -> CollectionCycleSummary:
    """Collect independently idempotent sources, backfill, then rank once."""

    loaded = load_settings(settings_path)
    collection_settings = loaded.settings.collection
    started_at = current_kst_time()
    slot = align_kst_slot(
        started_at,
        interval_hours=collection_settings.interval_hours,
        minute=collection_settings.slot_minute_kst,
    )
    engine = create_engine_from_env()
    try:
        results = tuple(
            _collect_source(engine, source, slot, started_at, loaded) for source in SOURCES
        )
        result_by_source_key = {result.source_key: result for result in results}
        eligible_backfill_sources = tuple(
            source
            for source in SOURCES
            if result_by_source_key[source.key].status
            in {"succeeded", "already_succeeded"}
        )
        backfill = _run_backfill_cycle(
            engine,
            slot,
            started_at,
            loaded,
            eligible_backfill_sources,
        )
        with session_scope(engine) as session:
            ranking_rows = refresh_cumulative(
                session,
                slot,
                loaded.settings.ranking.window_days,
                loaded.settings.ranking.top_n,
                loaded.config_version,
            )
        return CollectionCycleSummary(
            slot,
            results,
            ranking_rows,
            _cycle_status(results, backfill_failed=bool(backfill.failed_sources)),
        )
    finally:
        dispose_engine(engine)


def collect_and_rank_with_retries(
    settings_path: Path,
    *,
    sleep: Callable[[float], None] = time.sleep,
    random_delay: Callable[[float, float], float] = random.uniform,
) -> CollectionCycleSummary:
    loaded = load_settings(settings_path)
    collection = loaded.settings.collection
    for retry_index in range(collection.max_retries + 1):
        try:
            return collect_and_rank_once(settings_path)
        except _RETRYABLE_ERRORS:
            if retry_index >= collection.max_retries:
                raise
            sleep(
                random_delay(
                    collection.request_min_delay_seconds,
                    collection.request_max_delay_seconds,
                )
            )
    raise RuntimeError("retry loop exited unexpectedly")


def summary_payload(summary: CollectionCycleSummary) -> dict[str, object]:
    statuses = ("succeeded", "partial", "failed", "busy", "already_succeeded")
    return {
        "slot": summary.slot.isoformat(),
        "source_counts": {
            status: sum(source.status == status for source in summary.sources)
            for status in statuses
        },
        "total_pages_fetched": sum(source.pages_fetched for source in summary.sources),
        "total_accepted": sum(source.accepted for source in summary.sources),
        "ranking_rows": summary.ranking_rows,
        "status": summary.status,
    }


def _scheduled_cycle(settings_path: Path) -> None:
    try:
        summary = collect_and_rank_with_retries(settings_path)
    except Exception:
        print(json.dumps({"error": "collection_failed"}, sort_keys=True), flush=True)
        return
    print(json.dumps(summary_payload(summary), sort_keys=True), flush=True)


def build_scheduler(settings_path: Path) -> BlockingScheduler:
    loaded = load_settings(settings_path)
    collection = loaded.settings.collection
    scheduler = BlockingScheduler(timezone=KST)
    scheduler.add_job(
        _scheduled_cycle,
        trigger="cron",
        id="metadata-collection",
        args=(settings_path,),
        hour=schedule_hours(collection.interval_hours),
        minute=collection.slot_minute_kst,
        second=0,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=collection.interval_hours * 60 * 60,
        replace_existing=True,
    )
    return scheduler


def run_scheduler(settings_path: Path) -> None:
    scheduler = build_scheduler(settings_path)
    _scheduled_cycle(settings_path)
    scheduler.start()


def collector_health(max_age_hours: int) -> bool:
    engine = create_engine_from_env()
    try:
        with session_scope(engine) as session:
            return collector_is_healthy(
                session,
                now=current_kst_time(),
                max_age_hours=max_age_hours,
            )
    finally:
        dispose_engine(engine)
