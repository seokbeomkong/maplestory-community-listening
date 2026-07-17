import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

import maple_monitor.cli as cli
from maple_monitor.collection.client import ListPageTransportError
from maple_monitor.collection.repository import SnapshotConfigConflict


app = cli.app


def test_cli_help_is_available() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0, str(result.exception)
    assert "Operate the Maple Inven monitor" in result.output


def test_collect_command_redacts_client_failure_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leaked_detail = "token=do-not-leak https://user:secret@outside.example"

    def fail_fetch(board_id: int) -> bytes:
        raise ListPageTransportError(leaked_detail)

    def fail_engine() -> object:
        raise AssertionError("database must not be opened after fetch failure")

    monkeypatch.setattr(cli, "fetch_list_page", fail_fetch, raising=False)
    monkeypatch.setattr(cli, "create_engine_from_env", fail_engine)

    result = CliRunner().invoke(
        app,
        [
            "collect-metadata",
            "--board",
            "2294",
            "--at",
            "2026-07-14T06:20:00+09:00",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {"error": "collection_failed"}
    assert leaked_detail not in result.stdout
    assert "secret" not in result.stdout


@pytest.mark.parametrize(
    "at",
    [
        "2026-07-14T06:20:00",
        "2026-07-14T06:21:00+09:00",
        "0001-01-01T00:00:00+09:00",
        "not-a-time token=do-not-leak",
    ],
)
def test_collect_command_rejects_invalid_or_misaligned_time_before_fetch(
    monkeypatch: pytest.MonkeyPatch,
    at: str,
) -> None:
    def fail_fetch(board_id: int) -> bytes:
        raise AssertionError("invalid schedule input must not reach the network boundary")

    monkeypatch.setattr(cli, "fetch_list_page", fail_fetch, raising=False)

    result = CliRunner().invoke(
        app,
        ["collect-metadata", "--board", "2294", "--at", at],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {"error": "collection_failed"}
    assert "do-not-leak" not in result.stdout


def test_collect_command_redacts_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    leaked_detail = "configuration-secret-do-not-leak"
    invalid_settings = tmp_path / "invalid-settings.yaml"
    invalid_settings.write_text(f"unexpected: {leaked_detail}\n", encoding="utf-8")

    def fail_fetch(board_id: int) -> bytes:
        raise AssertionError("invalid settings must not reach the network boundary")

    monkeypatch.setattr(cli, "fetch_list_page", fail_fetch, raising=False)

    result = CliRunner().invoke(
        app,
        [
            "collect-metadata",
            "--board",
            "2294",
            "--at",
            "2026-07-14T06:20:00+09:00",
            "--settings",
            str(invalid_settings),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {"error": "collection_failed"}
    assert leaked_detail not in result.stdout


def test_collect_command_redacts_snapshot_config_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leaked_detail = "config=f" + "f" * 63 + " title=do-not-leak"

    class _Engine:
        disposed = False

        def dispose(self) -> None:
            self.disposed = True

    engine = _Engine()

    @contextmanager
    def fake_session_scope(active_engine: object) -> Iterator[object]:
        assert active_engine is engine
        yield object()

    def fail_collection(*args: object, **kwargs: object) -> object:
        raise SnapshotConfigConflict(leaked_detail)

    monkeypatch.setattr(
        cli,
        "fetch_list_page",
        lambda board_id: Path("tests/fixtures/list_warrior.html").read_bytes(),
    )
    monkeypatch.setattr(
        cli,
        "_current_kst_time",
        lambda: datetime(2026, 7, 14, 6, 25, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    monkeypatch.setattr(cli, "create_engine_from_env", lambda: engine)
    monkeypatch.setattr(cli, "session_scope", fake_session_scope)
    monkeypatch.setattr(cli, "collect_board_slot", fail_collection)

    result = CliRunner().invoke(
        app,
        [
            "collect-metadata",
            "--board",
            "2294",
            "--at",
            "2026-07-14T06:20:00+09:00",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {"error": "collection_failed"}
    assert leaked_detail not in result.stdout
    assert engine.disposed


def test_collect_and_rank_now_prints_a_bounded_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maple_monitor.ops.scheduler import CollectionCycleSummary, SourceCycleResult

    monkeypatch.setattr(
        cli,
        "collect_and_rank_with_retries",
        lambda settings: CollectionCycleSummary(
            slot=datetime(2026, 7, 15, 6, 20, tzinfo=ZoneInfo("Asia/Seoul")),
            sources=(
                SourceCycleResult("warrior", "succeeded", 2, 3, True),
                SourceCycleResult("magician", "failed", 0, 0, False),
                SourceCycleResult("archer", "already_succeeded", 0, 0, True),
            ),
            ranking_rows=9,
            status="partial",
        ),
        raising=False,
    )

    result = CliRunner().invoke(app, ["collect-and-rank", "--now"])

    assert result.exit_code == 0, str(result.exception)
    assert json.loads(result.stdout) == {
        "ranking_rows": 9,
        "slot": "2026-07-15T06:20:00+09:00",
        "source_counts": {
            "already_succeeded": 1,
            "busy": 0,
            "failed": 1,
            "partial": 0,
            "succeeded": 1,
        },
        "status": "partial",
        "total_accepted": 3,
        "total_pages_fetched": 2,
    }


def test_analyze_export_command_prints_refresh_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from maple_monitor.local.pipeline import RefreshSummary

    export = tmp_path / "production-20260717.zip"
    export.write_bytes(b"fixture")
    monkeypatch.setattr(
        cli,
        "refresh_analysis",
        lambda export_path, analysis_root: RefreshSummary(4, 4, 8, 0, 0, str(analysis_root)),
        raising=False,
    )

    result = CliRunner().invoke(
        app,
        [
            "analyze-export",
            "--export-path",
            str(export),
            "--analysis-root",
            str(tmp_path / "analysis"),
        ],
    )

    assert result.exit_code == 0, str(result.exception)
    assert json.loads(result.stdout)["analyzed_comments"] == 8
