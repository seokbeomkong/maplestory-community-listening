from runpy import run_path


def test_phase0_runs_all_configuration_and_database_checks() -> None:
    gates = run_path("scripts/gate.py")["GATES"]

    assert gates["phase0"] == [
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "pytest", "tests/unit/test_config.py", "-q"],
        ["uv", "run", "alembic", "upgrade", "head"],
        ["uv", "run", "pytest", "tests/integration/test_core_schema.py", "-q"],
    ]
