from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_PATHS = [
    _PROJECT_ROOT / "src",
    _PROJECT_ROOT / ".venv" / "Lib" / "site-packages",
    *(_PROJECT_ROOT / ".venv" / "lib").glob("python*/site-packages"),
]
_PROJECT_PATHS = [str(path) for path in _PROJECT_PATHS if path.is_dir()]
for _project_path in _PROJECT_PATHS:
    while _project_path in sys.path:
        sys.path.remove(_project_path)
sys.path[:0] = _PROJECT_PATHS

from maple_monitor.db_safety import UnsafeTestDatabaseUrlError  # noqa: E402
from maple_monitor.db_safety import validate_isolated_test_database_environment  # noqa: E402


GATES = {
    "phase0": [
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "pytest", "tests/unit/test_config.py", "-q"],
        ["uv", "run", "alembic", "upgrade", "head"],
        ["uv", "run", "pytest", "tests/integration/test_core_schema.py", "-q"],
    ],
}


def _phase0_database_preflight_error(
    value: str | None,
    environment: Mapping[str, str],
) -> str | None:
    try:
        validate_isolated_test_database_environment(value, environment)
    except UnsafeTestDatabaseUrlError as exc:
        return str(exc)
    return None


def _write_receipt(
    phase: str,
    results: list[dict[str, object]],
    *,
    error: dict[str, str] | None = None,
) -> tuple[dict[str, object], Path]:
    receipt: dict[str, object] = {
        "phase": phase,
        "finished_at": datetime.now(UTC).isoformat(),
        "passed": error is None and all(item["returncode"] == 0 for item in results),
        "results": results,
    }
    if error is not None:
        receipt["error"] = error
    output = Path(".test-receipts") / f"{phase}.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt, output


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) == 2 else ""
    if phase not in GATES:
        print(f"unknown gate: {phase}", file=sys.stderr)
        return 2

    results: list[dict[str, object]] = []
    for command in GATES[phase]:
        preflight_error = _phase0_database_preflight_error(
            os.environ.get("DATABASE_URL"),
            os.environ,
        )
        if phase == "phase0" and preflight_error is not None:
            receipt, output = _write_receipt(
                phase,
                results,
                error={"stage": "database_preflight", "message": preflight_error},
            )
            print(preflight_error, file=sys.stderr)
            print(f"FAIL {phase}; receipt={output}")
            return 1

        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        results.append({"command": command, "returncode": completed.returncode})
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        if completed.returncode:
            break
    receipt, output = _write_receipt(phase, results)
    print(f"{'PASS' if receipt['passed'] else 'FAIL'} {phase}; receipt={output}")
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
