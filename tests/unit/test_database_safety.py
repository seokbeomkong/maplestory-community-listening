from __future__ import annotations

import os
from pathlib import Path
from runpy import run_path
import subprocess
import sys

import pytest
from sqlalchemy.engine import URL


SAFE_DATABASE_URL = "postgresql+psycopg://maple_monitor:secret@127.0.0.1:55432/maple_monitor_test"
DANGEROUS_LIBPQ_ENVIRONMENT_VARIABLES = [
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGPASSWORD",
    "PGPASSFILE",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGSYSCONFDIR",
    "PGOPTIONS",
    "PGTARGETSESSIONATTRS",
    "PGLOADBALANCEHOSTS",
    "PGSSLNEGOTIATION",
    "PGSSLMODE",
    "PGREQUIRESSL",
    "PGSSLCOMPRESSION",
    "PGSSLCERT",
    "PGSSLKEY",
    "PGSSLCERTMODE",
    "PGSSLROOTCERT",
    "PGSSLCRL",
    "PGSSLCRLDIR",
    "PGSSLSNI",
    "PGREQUIREPEER",
    "PGSSLMINPROTOCOLVERSION",
    "PGSSLMAXPROTOCOLVERSION",
    "PGREQUIREAUTH",
    "PGCHANNELBINDING",
    "PGGSSENCMODE",
    "PGKRBSRVNAME",
    "PGGSSLIB",
    "PGGSSDELEGATION",
    "PGMINPROTOCOLVERSION",
    "PGMAXPROTOCOLVERSION",
    "PGOAUTHDEBUG",
    "PGOAUTHCAFILE",
    "PGAPPNAME",
    "PGCONNECT_TIMEOUT",
    "PGCLIENTENCODING",
    "PGDATESTYLE",
    "PGTZ",
    "PGGEQO",
    "PGLOCALEDIR",
    "pghostaddr",
    "PgService",
    "PGFUTURE_ROUTING_OVERRIDE",
]


def _clear_dangerous_libpq_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable_name in tuple(os.environ):
        if variable_name.casefold().startswith("pg"):
            monkeypatch.delenv(variable_name, raising=False)


def test_no_fixture_alembic_test_runs_preflight_before_database_capable_call(
    tmp_path: Path,
) -> None:
    assertion_bomb = "DATABASE_CAPABLE_ALEMBIC_CALL_REACHED"
    call_sentinel = tmp_path / "alembic-check-called"
    plugin = tmp_path / "preflight_assertion_bomb.py"
    plugin.write_text(
        "from pathlib import Path\n"
        "from alembic import command\n\n"
        "def pytest_configure(config):\n"
        "    def assertion_bomb(*args, **kwargs):\n"
        f"        Path({str(call_sentinel)!r}).touch()\n"
        f"        raise AssertionError({assertion_bomb!r})\n"
        "    command.check = assertion_bomb\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["DATABASE_URL"] = (
        "postgresql+psycopg://user:preflight-secret@127.0.0.1:55432/"
        "maple_monitor_test?host=203.0.113.10"
    )
    environment["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(tmp_path), environment.get("PYTHONPATH")) if value
    )
    environment.pop("PYTEST_ADDOPTS", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            plugin.stem,
            "tests/integration/test_core_schema.py::"
            "test_alembic_metadata_does_not_treat_runtime_partitions_as_schema_drift",
            "-q",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    output = result.stdout + result.stderr

    assert not call_sentinel.exists(), output
    assert result.returncode == 1
    assert "DATABASE_URL must target the isolated PostgreSQL test database" in output
    assert assertion_bomb not in output


def test_no_fixture_alembic_test_rejects_libpq_environment_before_database_capable_call(
    tmp_path: Path,
) -> None:
    assertion_bomb = "DATABASE_CAPABLE_ALEMBIC_CALL_REACHED"
    call_sentinel = tmp_path / "alembic-check-called"
    plugin = tmp_path / "preflight_assertion_bomb.py"
    plugin.write_text(
        "from pathlib import Path\n"
        "from alembic import command\n\n"
        "def pytest_configure(config):\n"
        "    def assertion_bomb(*args, **kwargs):\n"
        f"        Path({str(call_sentinel)!r}).touch()\n"
        f"        raise AssertionError({assertion_bomb!r})\n"
        "    command.check = assertion_bomb\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    for variable_name in tuple(environment):
        if variable_name.casefold().startswith("pg"):
            environment.pop(variable_name)
    environment["DATABASE_URL"] = SAFE_DATABASE_URL
    environment["PGHOSTADDR"] = "203.0.113.10"
    environment["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(tmp_path), environment.get("PYTHONPATH")) if value
    )
    environment.pop("PYTEST_ADDOPTS", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            plugin.stem,
            "tests/integration/test_core_schema.py::"
            "test_alembic_metadata_does_not_treat_runtime_partitions_as_schema_drift",
            "-q",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    output = result.stdout + result.stderr

    assert not call_sentinel.exists(), output
    assert result.returncode == 1
    assert "libpq environment overrides are not allowed" in output
    assert assertion_bomb not in output
    assert "PGHOSTADDR" not in output
    assert "203.0.113.10" not in output


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+psycopg://user:secret@127.0.0.1:55432/maple_monitor_test?host=remote",
        "postgresql+psycopg://user:secret@localhost:55432/maple_monitor_test?dbname=prod",
        "postgresql+psycopg://user:secret@localhost:55432/maple_monitor_test?service=prod",
        "postgresql+psycopg://user:secret@localhost:55432/maple_monitor_test?"
        "conninfo=hostaddr%3D203.0.113.10",
        "postgresql://user:secret@localhost:55432/maple_monitor_test?dsn=hostaddr%3D203.0.113.10",
        "postgresql+psycopg://user:secret@localhost:55432/%6daple_monitor_test",
        "postgresql+psycopg://user:secret@localhost:55432/maple_monitor_test#",
        "postgresql+psycopg://user:secret@localhost:55432/maple_monitor_\ntest",
        "postgresql+psycopg://user:secret\x00@localhost:55432/maple_monitor_test",
        "postgresql+psycopg://user:secret\x7f@localhost:55432/maple_monitor_test",
        "postgresql+psycopg://user:secret%0A@localhost:55432/maple_monitor_test",
        "postgresql+psycopg://user:secret%FF@localhost:55432/maple_monitor_test",
        "postgresql+psycopg://user:secret@localhost:55432/maple_monitor_test?%68ost=remote",
        "postgresql+psycopg://user:secret@localhost:70000/maple_monitor_test",
    ],
)
def test_shared_validator_rejects_sqlalchemy_routing_and_parser_differentials(
    database_url: str,
) -> None:
    from maple_monitor.db_safety import UnsafeTestDatabaseUrlError
    from maple_monitor.db_safety import validate_isolated_test_database_url

    with pytest.raises(UnsafeTestDatabaseUrlError, match="isolated PostgreSQL test database"):
        validate_isolated_test_database_url(database_url)


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+psycopg://maple_monitor:secret@127.0.0.1:55432/maple_monitor_test",
        "postgresql://alternate_user@localhost:5433/maple_monitor_test?connect_timeout=1",
        "postgresql+psycopg://user:p%23ss@[::1]:5432/maple_monitor_test",
    ],
)
def test_shared_validator_returns_sqlalchemy_url_for_safe_local_contract(
    database_url: str,
) -> None:
    from maple_monitor.db_safety import validate_isolated_test_database_url

    validated = validate_isolated_test_database_url(database_url)

    assert isinstance(validated, URL)
    assert validated.database == "maple_monitor_test"


@pytest.mark.parametrize("variable_name", DANGEROUS_LIBPQ_ENVIRONMENT_VARIABLES)
def test_shared_environment_validator_rejects_each_dangerous_libpq_variable_without_echo(
    variable_name: str,
) -> None:
    from maple_monitor.db_safety import UnsafeTestDatabaseUrlError
    from maple_monitor.db_safety import validate_isolated_test_database_environment

    variable_value = f"sensitive-{variable_name.casefold()}-value"

    with pytest.raises(UnsafeTestDatabaseUrlError) as error:
        validate_isolated_test_database_environment(
            SAFE_DATABASE_URL,
            {variable_name: variable_value},
        )

    assert str(error.value) == (
        "libpq environment overrides are not allowed for the isolated PostgreSQL test database"
    )
    assert variable_name not in str(error.value)
    assert variable_value not in str(error.value)


def test_shared_environment_validator_allows_empty_overrides_and_harmless_environment() -> None:
    from maple_monitor.db_safety import validate_isolated_test_database_environment

    environment = {name: "" for name in DANGEROUS_LIBPQ_ENVIRONMENT_VARIABLES}
    environment.update(
        {
            "UNRELATED_TEST_SETTING": "allowed",
            "MAPLE_MONITOR_TEST_LABEL": "harmless",
        }
    )

    validated = validate_isolated_test_database_environment(SAFE_DATABASE_URL, environment)

    assert validated.database == "maple_monitor_test"


def test_environment_policy_classifies_every_installed_libpq_variable() -> None:
    from psycopg import pq

    installed_libpq_variables = {
        option.envvar.decode() for option in pq.Conninfo.get_defaults() if option.envvar
    }

    assert installed_libpq_variables <= set(DANGEROUS_LIBPQ_ENVIRONMENT_VARIABLES)


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+psycopg://user:fixture-host-secret@127.0.0.1:55432/"
        "maple_monitor_test?host=203.0.113.10",
        "postgresql+psycopg://user:fixture-database-secret@127.0.0.1:55432/"
        "maple_monitor_test?dbname=production",
        "postgresql+psycopg://user:fixture-conninfo-secret@127.0.0.1:55432/"
        "maple_monitor_test?conninfo=hostaddr%3D203.0.113.10",
        "postgresql://user:fixture-dsn-secret@127.0.0.1:55432/"
        "maple_monitor_test?dsn=hostaddr%3D203.0.113.10",
    ],
)
def test_integration_engine_fixture_rejects_routing_override_before_engine_creation(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integration_fixtures = run_path("tests/integration/conftest.py")
    created_urls: list[str] = []

    def record_forbidden_engine(url: str, **_kwargs: object) -> None:
        created_urls.append(url)
        raise AssertionError("unsafe integration fixture created an engine")

    fixture_function = integration_fixtures["db_engine"].__wrapped__
    monkeypatch.setitem(fixture_function.__globals__, "create_engine", record_forbidden_engine)

    fixture_generator = fixture_function(database_url)
    with pytest.raises(pytest.fail.Exception, match="isolated PostgreSQL test database"):
        next(fixture_generator)

    assert created_urls == []


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
def test_integration_engine_fixture_rejects_unsafe_libpq_environment_before_engine_creation(
    variable_name: str,
    variable_value: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integration_fixtures = run_path("tests/integration/conftest.py")
    _clear_dangerous_libpq_environment(monkeypatch)
    monkeypatch.setenv(variable_name, variable_value)
    created_urls: list[str] = []

    def record_forbidden_engine(url: str, **_kwargs: object) -> None:
        created_urls.append(url)
        raise AssertionError("unsafe integration fixture created an engine")

    fixture_function = integration_fixtures["db_engine"].__wrapped__
    monkeypatch.setitem(fixture_function.__globals__, "create_engine", record_forbidden_engine)

    fixture_generator = fixture_function(SAFE_DATABASE_URL)
    with pytest.raises(pytest.fail.Exception, match="isolated PostgreSQL test database"):
        next(fixture_generator)

    assert created_urls == []


def test_integration_autouse_preflight_and_engine_allow_harmless_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integration_fixtures = run_path("tests/integration/conftest.py")
    _clear_dangerous_libpq_environment(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", SAFE_DATABASE_URL)
    monkeypatch.setenv("MAPLE_MONITOR_TEST_LABEL", "harmless")

    preflight_fixture = integration_fixtures["database_environment_preflight"]
    assert preflight_fixture._fixture_function_marker.autouse is True
    assert preflight_fixture._fixture_function_marker.scope == "function"
    preflight_fixture.__wrapped__()

    database_url_fixture = integration_fixtures["database_url"].__wrapped__
    assert database_url_fixture() == SAFE_DATABASE_URL

    class ScalarResult:
        def scalar_one(self) -> int:
            return 1

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, _statement: object) -> ScalarResult:
            return ScalarResult()

    class FakeEngine:
        def __init__(self) -> None:
            self.disposed = False

        def connect(self) -> FakeConnection:
            return FakeConnection()

        def dispose(self) -> None:
            self.disposed = True

    fake_engine = FakeEngine()
    created_urls: list[str] = []

    def create_fake_engine(url: str, **_kwargs: object) -> FakeEngine:
        created_urls.append(url)
        return fake_engine

    fixture_function = integration_fixtures["db_engine"].__wrapped__
    monkeypatch.setitem(fixture_function.__globals__, "create_engine", create_fake_engine)
    fixture_generator = fixture_function(SAFE_DATABASE_URL)

    assert next(fixture_generator) is fake_engine
    with pytest.raises(StopIteration):
        next(fixture_generator)
    assert created_urls == [SAFE_DATABASE_URL]
    assert fake_engine.disposed is True


def test_integration_database_url_fixture_uses_shared_fail_closed_missing_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maple_monitor.db_safety import UnsafeTestDatabaseUrlError

    integration_fixtures = run_path("tests/integration/conftest.py")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    fixture_function = integration_fixtures["database_url"].__wrapped__
    validated_values: list[str | None] = []

    def reject_missing(value: str | None, _environment: object) -> None:
        validated_values.append(value)
        raise UnsafeTestDatabaseUrlError("shared validator sentinel")

    monkeypatch.setitem(
        fixture_function.__globals__, "validate_isolated_test_database_environment", reject_missing
    )

    with pytest.raises(pytest.fail.Exception, match="shared validator sentinel"):
        fixture_function()

    assert validated_values == [None]
