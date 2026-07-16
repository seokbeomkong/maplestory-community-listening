from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

import maple_monitor.ops.scheduler as scheduler
from maple_monitor.collection.backfill import BackfillBudgetSummary
from maple_monitor.collection.client import ListPageTransportError
from maple_monitor.collection.pagination import IncrementalScanResult
from maple_monitor.collection.types import CollectionSummary
from maple_monitor.config import load_settings
from maple_monitor.ops.run_control import RunClaim
from maple_monitor.sources import SOURCES


KST = ZoneInfo("Asia/Seoul")
SLOT = datetime(2026, 7, 15, 6, 20, tzinfo=KST)


class _Connection:
    def close(self) -> None:
        pass


class _Engine:
    def connect(self) -> _Connection:
        return _Connection()


def _install_cycle_fakes(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[str]]:
    loaded = load_settings(Path("config/settings.yaml"))
    claimed: list[str] = []
    finished: list[str] = []

    @contextmanager
    def fake_session_scope(engine: object) -> Iterator[object]:
        yield object()

    monkeypatch.setattr(scheduler, "SOURCES", SOURCES[:2])
    monkeypatch.setattr(scheduler, "load_settings", lambda path: loaded)
    monkeypatch.setattr(scheduler, "current_kst_time", lambda: SLOT)
    monkeypatch.setattr(scheduler, "create_engine_from_env", _Engine)
    monkeypatch.setattr(scheduler, "session_scope", fake_session_scope)
    monkeypatch.setattr(scheduler, "try_collector_lock", lambda connection, key: True)
    monkeypatch.setattr(scheduler, "release_collector_lock", lambda connection, key: None)
    monkeypatch.setattr(scheduler, "dispose_engine", lambda engine: None)
    monkeypatch.setattr(scheduler, "highest_ordinary_post_id", lambda session, board_id: None)

    def claim(*args: object, **kwargs: object) -> RunClaim:
        claimed.append(str(kwargs["job_type"]))
        return RunClaim(UUID(int=len(claimed)), "acquired", 1, 0)

    monkeypatch.setattr(scheduler, "claim_run_slot", claim)
    monkeypatch.setattr(
        scheduler,
        "finish_run",
        lambda *args, **kwargs: finished.append(str(kwargs["status"])),
    )
    monkeypatch.setattr(
        scheduler,
        "collect_board_slot",
        lambda *args, **kwargs: CollectionSummary(1, 0, 0, 0),
    )
    monkeypatch.setattr(
        scheduler,
        "run_backfill_budget",
        lambda *args, **kwargs: BackfillBudgetSummary(0, 0, ()),
    )
    monkeypatch.setattr(
        scheduler,
        "_run_backfill_cycle",
        lambda *args, **kwargs: BackfillBudgetSummary(0, 0, ()),
        raising=False,
    )
    monkeypatch.setattr(scheduler, "refresh_cumulative", lambda *args, **kwargs: 9)
    return claimed, finished


def test_schedule_hours_are_derived_from_the_configured_interval() -> None:
    assert scheduler.schedule_hours(6) == "0,6,12,18"
    assert scheduler.schedule_hours(8) == "0,8,16"


def test_source_failure_is_partial_and_later_source_still_commits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claimed, finished = _install_cycle_fakes(monkeypatch)

    def scan(source: object, *args: object, **kwargs: object) -> IncrementalScanResult:
        if getattr(source, "key") == "warrior":
            raise ListPageTransportError("redacted upstream")
        return IncrementalScanResult((), 2, True, 20, "succeeded")

    monkeypatch.setattr(scheduler, "scan_incremental_pages", scan)

    result = scheduler.collect_and_rank_once(Path("config/settings.yaml"))

    assert claimed == ["metadata:warrior", "metadata:magician"]
    assert finished == ["failed", "succeeded"]
    assert [source.status for source in result.sources] == ["failed", "succeeded"]
    assert result.ranking_rows == 9
    assert result.status == "partial"


def test_successful_source_slot_replay_performs_no_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_cycle_fakes(monkeypatch)
    monkeypatch.setattr(scheduler, "SOURCES", SOURCES[:1])
    monkeypatch.setattr(
        scheduler,
        "claim_run_slot",
        lambda *args, **kwargs: RunClaim(UUID(int=1), "already_succeeded", 1, 4),
    )
    monkeypatch.setattr(
        scheduler,
        "scan_incremental_pages",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not fetch")),
    )

    result = scheduler.collect_and_rank_once(Path("config/settings.yaml"))

    assert result.sources[0].status == "already_succeeded"


def test_page_guard_partial_does_not_store_or_finish_succeeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, finished = _install_cycle_fakes(monkeypatch)
    monkeypatch.setattr(scheduler, "SOURCES", SOURCES[:1])
    monkeypatch.setattr(
        scheduler,
        "scan_incremental_pages",
        lambda *args, **kwargs: IncrementalScanResult((), 100, False, 10, "partial"),
    )
    monkeypatch.setattr(
        scheduler,
        "collect_board_slot",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("partial must not store")),
    )

    result = scheduler.collect_and_rank_once(Path("config/settings.yaml"))

    assert finished == ["partial"]
    assert result.sources[0].status == "partial"
    assert result.status == "failed"


def test_backfill_receives_only_sources_with_completed_incremental_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    durable_backfill_cycle = scheduler._run_backfill_cycle
    _install_cycle_fakes(monkeypatch)
    monkeypatch.setattr(scheduler, "_run_backfill_cycle", durable_backfill_cycle)
    selected_sources = SOURCES[:5]
    monkeypatch.setattr(scheduler, "SOURCES", selected_sources)
    statuses = {
        "warrior": "failed",
        "magician": "already_succeeded",
        "archer": "partial",
        "thief": "succeeded",
        "pirate": "busy",
    }
    monkeypatch.setattr(
        scheduler,
        "_collect_source",
        lambda engine, source, slot, started_at, loaded: scheduler.SourceCycleResult(
            source.key,
            statuses[source.key],
            0,
            0,
            statuses[source.key] in {"succeeded", "already_succeeded"},
        ),
    )
    backfill_sources: list[tuple[str, ...]] = []

    def backfill(*args: object, sources: object, **kwargs: object) -> BackfillBudgetSummary:
        backfill_sources.append(tuple(source.key for source in sources))
        return BackfillBudgetSummary(0, 0, ())

    monkeypatch.setattr(scheduler, "run_backfill_budget", backfill)

    scheduler.collect_and_rank_once(Path("config/settings.yaml"))

    assert backfill_sources == [("magician", "thief")]


def test_backfill_receives_no_sources_when_every_incremental_slot_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    durable_backfill_cycle = scheduler._run_backfill_cycle
    _install_cycle_fakes(monkeypatch)
    monkeypatch.setattr(scheduler, "_run_backfill_cycle", durable_backfill_cycle)
    selected_sources = SOURCES[:3]
    monkeypatch.setattr(scheduler, "SOURCES", selected_sources)
    statuses = {"warrior": "failed", "magician": "partial", "archer": "busy"}
    monkeypatch.setattr(
        scheduler,
        "_collect_source",
        lambda engine, source, slot, started_at, loaded: scheduler.SourceCycleResult(
            source.key,
            statuses[source.key],
            0,
            0,
            False,
        ),
    )
    backfill_sources: list[tuple[str, ...]] = []

    def backfill(*args: object, sources: object, **kwargs: object) -> BackfillBudgetSummary:
        backfill_sources.append(tuple(source.key for source in sources))
        return BackfillBudgetSummary(0, 0, ())

    monkeypatch.setattr(scheduler, "run_backfill_budget", backfill)

    scheduler.collect_and_rank_once(Path("config/settings.yaml"))

    assert backfill_sources == [()]


def test_scheduler_registers_one_non_overlapping_cron_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = load_settings(Path("config/settings.yaml"))
    monkeypatch.setattr(scheduler, "load_settings", lambda path: loaded)
    instance = scheduler.build_scheduler(Path("config/settings.yaml"))
    job = instance.get_job("metadata-collection")
    assert job is not None
    assert str(job.trigger) == "cron[hour='0,6,12,18', minute='20', second='0']"
    assert job.max_instances == 1
    assert job.coalesce is True


def test_retry_wrapper_retries_transient_failure_with_bounded_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = load_settings(Path("config/settings.yaml"))
    attempts = 0
    delays: list[float] = []
    expected = scheduler.CollectionCycleSummary(SLOT, (), 9, "succeeded")

    def sometimes_fails(settings_path: Path) -> scheduler.CollectionCycleSummary:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ListPageTransportError("transient secret")
        return expected

    monkeypatch.setattr(scheduler, "load_settings", lambda path: loaded)
    monkeypatch.setattr(scheduler, "collect_and_rank_once", sometimes_fails)
    result = scheduler.collect_and_rank_with_retries(
        Path("config/settings.yaml"),
        sleep=delays.append,
        random_delay=lambda low, high: high,
    )
    assert result is expected
    assert attempts == 3
    assert delays == [3.0, 3.0]


def test_retry_wrapper_does_not_retry_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scheduler,
        "load_settings",
        lambda path: (_ for _ in ()).throw(ValueError("invalid configuration")),
    )
    with pytest.raises(ValueError, match="invalid configuration"):
        scheduler.collect_and_rank_with_retries(Path("config/settings.yaml"))


def test_ranking_retry_preserves_partial_backfill_outcome_without_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    durable_backfill_cycle = scheduler._run_backfill_cycle
    _install_cycle_fakes(monkeypatch)
    monkeypatch.setattr(scheduler, "_run_backfill_cycle", durable_backfill_cycle)
    monkeypatch.setattr(scheduler, "SOURCES", SOURCES[:1])
    monkeypatch.setattr(
        scheduler,
        "_collect_source",
        lambda *args, **kwargs: scheduler.SourceCycleResult(
            "warrior", "succeeded", 2, 1, True
        ),
    )

    backfill_run_id = UUID(int=99)
    pages_consumed = 0
    backfill_succeeded = False
    persisted_failed_sources: tuple[str, ...] = ()
    fetches: list[int] = []
    ranking_attempts = 0

    def claim(*args: object, **kwargs: object) -> object:
        assert kwargs["job_type"] == "metadata-backfill"
        return SimpleNamespace(
            run_id=backfill_run_id,
            disposition="already_succeeded" if backfill_succeeded else "acquired",
            attempts=1,
            pages_consumed=pages_consumed,
            accepted=0,
            failed_sources=persisted_failed_sources,
        )

    def reserve(*args: object, **kwargs: object) -> int | None:
        nonlocal pages_consumed
        if pages_consumed >= int(kwargs["page_budget"]):
            return None
        pages_consumed += 1
        return pages_consumed

    def backfill(*args: object, **kwargs: object) -> BackfillBudgetSummary:
        reserve_page = kwargs["reserve_page"]
        while reserve_page():
            fetches.append(len(fetches) + 1)
        return BackfillBudgetSummary(len(fetches), 0, ("free",))

    def finish(*args: object, **kwargs: object) -> None:
        nonlocal backfill_succeeded, persisted_failed_sources
        assert kwargs["run_id"] == backfill_run_id
        assert kwargs["status"] == "succeeded"
        diagnostics = kwargs["diagnostics"]
        persisted_failed_sources = tuple(diagnostics["failed_sources"])
        backfill_succeeded = True

    def rank(*args: object, **kwargs: object) -> int:
        nonlocal ranking_attempts
        ranking_attempts += 1
        if ranking_attempts == 1:
            raise scheduler.SQLAlchemyError("ranking failed")
        return 9

    monkeypatch.setattr(scheduler, "claim_run_slot", claim)
    monkeypatch.setattr(scheduler, "reserve_run_page", reserve, raising=False)
    monkeypatch.setattr(scheduler, "run_backfill_budget", backfill)
    monkeypatch.setattr(scheduler, "finish_run", finish)
    monkeypatch.setattr(scheduler, "refresh_cumulative", rank)

    result = scheduler.collect_and_rank_with_retries(
        Path("config/settings.yaml"),
        sleep=lambda delay: None,
        random_delay=lambda low, high: low,
    )

    assert result.ranking_rows == 9
    assert result.status == "partial"
    assert ranking_attempts == 2
    assert len(fetches) == 40
