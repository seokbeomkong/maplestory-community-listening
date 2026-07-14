from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from runpy import run_path

import pytest


PHASE0_COMMANDS = [
    ["uv", "run", "ruff", "check", "."],
    ["uv", "run", "pytest", "tests/unit/test_config.py", "-q"],
    ["uv", "run", "alembic", "upgrade", "head"],
    ["uv", "run", "pytest", "tests/integration/test_core_schema.py", "-q"],
]


def _clear_postgresql_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable_name in tuple(os.environ):
        if variable_name.casefold().startswith("pg"):
            monkeypatch.delenv(variable_name, raising=False)


def test_phase0_runs_all_configuration_and_database_checks() -> None:
    gates = run_path("scripts/gate.py")["GATES"]

    assert gates["phase0"] == PHASE0_COMMANDS


@pytest.mark.parametrize(
    ("database_url", "secret"),
    [
        (None, None),
        ("", None),
        ("not-a-database-url", None),
        (
            "postgresql+psycopg://maple_monitor:malformed-percent-secret-%ZZ@"
            "127.0.0.1:55432/maple_monitor_test",
            "malformed-percent-secret",
        ),
        (
            "postgresql+psycopg://maple_monitor:remote-host-secret@"
            "203.0.113.10:5432/maple_monitor_test",
            "remote-host-secret",
        ),
        (
            "postgresql+psycopg://maple_monitor:production-name-secret@"
            "127.0.0.1:55432/maple_monitor",
            "production-name-secret",
        ),
        ("sqlite:///maple_monitor_test", None),
        (
            "postgresql+psycopg://maple_monitor:query-host-secret@127.0.0.1:55432/"
            "maple_monitor_test?host=203.0.113.10",
            "query-host-secret",
        ),
        (
            "postgresql+psycopg://maple_monitor:query-database-secret@127.0.0.1:55432/"
            "maple_monitor_test?dbname=production",
            "query-database-secret",
        ),
        (
            "postgresql+psycopg://maple_monitor:query-conninfo-secret@127.0.0.1:55432/"
            "maple_monitor_test?conninfo=hostaddr%3D203.0.113.10",
            "query-conninfo-secret",
        ),
        (
            "postgresql://maple_monitor:query-dsn-secret@127.0.0.1:55432/"
            "maple_monitor_test?dsn=hostaddr%3D203.0.113.10",
            "query-dsn-secret",
        ),
        (
            "postgresql+psycopg://maple_monitor:encoded-database-secret@127.0.0.1:55432/"
            "%6daple_monitor_test",
            "encoded-database-secret",
        ),
        (
            "postgresql+psycopg://maple_monitor:fragment-secret@127.0.0.1:55432/"
            "maple_monitor_test#",
            "fragment-secret",
        ),
        (
            "postgresql+psycopg://maple_monitor:newline-secret@127.0.0.1:55432/"
            "maple_monitor_\ntest",
            "newline-secret",
        ),
        (
            "postgresql+psycopg://maple_monitor:delete-control-secret\x7f@"
            "127.0.0.1:55432/maple_monitor_test",
            "delete-control-secret",
        ),
        (
            "postgresql+psycopg://maple_monitor:encoded-control-secret%0A@"
            "127.0.0.1:55432/maple_monitor_test",
            "encoded-control-secret",
        ),
    ],
    ids=[
        "missing",
        "empty",
        "malformed",
        "malformed-percent-escape",
        "remote",
        "non-test-database",
        "non-postgresql",
        "query-host-route-override",
        "query-database-route-override",
        "query-conninfo-route-override",
        "query-dsn-route-override",
        "percent-encoded-database",
        "raw-empty-fragment",
        "internal-newline",
        "delete-control-character",
        "percent-encoded-control-character",
    ],
)
def test_phase0_rejects_unsafe_database_url_before_any_command(
    database_url: str | None,
    secret: str | None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    gate = run_path("scripts/gate.py")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["scripts/gate.py", "phase0"])
    if database_url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", database_url)

    launched_commands: list[list[str]] = []

    def record_forbidden_command(command: list[str], **_kwargs: object) -> None:
        launched_commands.append(command)
        raise AssertionError(f"unsafe preflight launched command: {command}")

    monkeypatch.setattr(subprocess, "run", record_forbidden_command)

    exit_code = gate["main"]()

    assert exit_code == 1
    assert launched_commands == []
    receipt_text = (tmp_path / ".test-receipts" / "phase0.json").read_text()
    receipt = json.loads(receipt_text)
    assert receipt["phase"] == "phase0"
    assert receipt["passed"] is False
    assert receipt["results"] == []
    assert receipt["error"]["stage"] == "database_preflight"
    assert "DATABASE_URL" in receipt["error"]["message"]
    output = capsys.readouterr()
    assert "FAIL phase0" in output.out
    assert receipt["error"]["message"] in output.err
    for captured in (output.out, output.err, receipt_text):
        if database_url:
            assert database_url not in captured
        if secret:
            assert secret not in captured


@pytest.mark.parametrize(
    ("variable_name", "variable_value"),
    [
        ("PGHOSTADDR", "203.0.113.10"),
        ("PGSERVICE", "production-service"),
        ("PGOPTIONS", "-c search_path=production_schema"),
        ("PGOAUTHDEBUG", "UNSAFE"),
        ("PGOAUTHCAFILE", "sensitive-oauth-ca-file"),
        ("pghostaddr", "203.0.113.10"),
        ("PgService", "production-service"),
        ("PGFUTURE_ROUTING_OVERRIDE", "sensitive-future-value"),
    ],
)
def test_phase0_rejects_unsafe_libpq_environment_before_any_command(
    variable_name: str,
    variable_value: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    gate = run_path("scripts/gate.py")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["scripts/gate.py", "phase0"])
    _clear_postgresql_environment(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://maple_monitor:secret@127.0.0.1:55432/maple_monitor_test",
    )
    monkeypatch.setenv(variable_name, variable_value)
    launched_commands: list[list[str]] = []

    def record_forbidden_command(command: list[str], **_kwargs: object) -> None:
        launched_commands.append(command)
        raise AssertionError(f"unsafe preflight launched command: {command}")

    monkeypatch.setattr(subprocess, "run", record_forbidden_command)

    exit_code = gate["main"]()

    assert exit_code == 1
    assert launched_commands == []
    receipt_text = (tmp_path / ".test-receipts" / "phase0.json").read_text()
    receipt = json.loads(receipt_text)
    assert receipt["passed"] is False
    assert receipt["results"] == []
    assert receipt["error"]["stage"] == "database_preflight"
    output = capsys.readouterr()
    for captured in (output.out, output.err, receipt_text):
        assert variable_name not in captured
        assert variable_value not in captured


@pytest.mark.parametrize(
    "database_url",
    [
        ("postgresql+psycopg://maple_monitor:maple_monitor@127.0.0.1:55432/maple_monitor_test"),
        "postgresql://alternate_user@localhost:5433/maple_monitor_test?connect_timeout=1",
    ],
    ids=["compose-url", "equivalent-loopback-contract"],
)
def test_phase0_valid_local_database_runs_exactly_four_successful_commands(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    gate = run_path("scripts/gate.py")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["scripts/gate.py", "phase0"])
    _clear_postgresql_environment(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("MAPLE_MONITOR_TEST_LABEL", "harmless")
    launched_commands: list[list[str]] = []

    def succeed(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        launched_commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", succeed)

    assert gate["main"]() == 0
    assert launched_commands == PHASE0_COMMANDS
    receipt = json.loads((tmp_path / ".test-receipts" / "phase0.json").read_text())
    assert receipt["passed"] is True
    assert receipt["results"] == [
        {"command": command, "returncode": 0} for command in PHASE0_COMMANDS
    ]


def test_phase0_revalidates_environment_before_each_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    gate = run_path("scripts/gate.py")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["scripts/gate.py", "phase0"])
    _clear_postgresql_environment(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://maple_monitor:secret@127.0.0.1:55432/maple_monitor_test",
    )
    launched_commands: list[list[str]] = []

    def succeed_once_then_poison_environment(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        launched_commands.append(command)
        monkeypatch.setenv("PGHOSTADDR", "203.0.113.10")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", succeed_once_then_poison_environment)

    assert gate["main"]() == 1
    assert launched_commands == [PHASE0_COMMANDS[0]]
    receipt_text = (tmp_path / ".test-receipts" / "phase0.json").read_text()
    receipt = json.loads(receipt_text)
    assert receipt["passed"] is False
    assert receipt["results"] == [{"command": PHASE0_COMMANDS[0], "returncode": 0}]
    assert receipt["error"]["stage"] == "database_preflight"
    output = capsys.readouterr()
    for captured in (output.out, output.err, receipt_text):
        assert "PGHOSTADDR" not in captured
        assert "203.0.113.10" not in captured
