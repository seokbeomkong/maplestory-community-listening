import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import maple_monitor.cli as cli
from maple_monitor.collection.client import ListPageTransportError


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
