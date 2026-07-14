from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit


GATES = {
    "phase0": [
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "pytest", "tests/unit/test_config.py", "-q"],
        ["uv", "run", "alembic", "upgrade", "head"],
        ["uv", "run", "pytest", "tests/integration/test_core_schema.py", "-q"],
    ],
}

_PHASE0_DATABASE_SCHEMES = {"postgresql", "postgresql+psycopg"}
_PHASE0_DATABASE_HOSTS = {"127.0.0.1", "::1", "localhost"}
_PHASE0_DATABASE_NAME = "maple_monitor_test"
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_DATABASE_ROUTE_QUERY_KEYS = {
    "database",
    "dbname",
    "host",
    "hostaddr",
    "password",
    "port",
    "service",
    "servicefile",
    "user",
}


def _phase0_database_preflight_error(value: str | None) -> str | None:
    error = "DATABASE_URL must target the isolated PostgreSQL test database on loopback"
    if value is None or not value.strip():
        return f"{error}; DATABASE_URL is missing"
    if _INVALID_PERCENT_ESCAPE.search(value):
        return f"{error}; DATABASE_URL is malformed"

    try:
        url = urlsplit(value)
        host = url.hostname
        _port = url.port
        unquote(url.username or "", errors="strict")
        unquote(url.password or "", errors="strict")
        database = unquote(url.path.removeprefix("/"), errors="strict")
        query_keys = {
            key.lower()
            for key, _value in parse_qsl(url.query, keep_blank_values=True, errors="strict")
        }
    except (UnicodeError, ValueError):
        return f"{error}; DATABASE_URL is malformed"

    if (
        url.scheme not in _PHASE0_DATABASE_SCHEMES
        or host not in _PHASE0_DATABASE_HOSTS
        or database != _PHASE0_DATABASE_NAME
        or bool(url.fragment)
        or bool(query_keys & _DATABASE_ROUTE_QUERY_KEYS)
    ):
        return error
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

    preflight_error = _phase0_database_preflight_error(os.environ.get("DATABASE_URL"))
    if phase == "phase0" and preflight_error is not None:
        receipt, output = _write_receipt(
            phase,
            [],
            error={"stage": "database_preflight", "message": preflight_error},
        )
        print(preflight_error, file=sys.stderr)
        print(f"FAIL {phase}; receipt={output}")
        return 1

    results: list[dict[str, object]] = []
    for command in GATES[phase]:
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
