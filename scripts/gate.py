from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


GATES = {
    "phase0": [
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "pytest", "tests/unit/test_config.py", "-q"],
    ],
}


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) == 2 else ""
    if phase not in GATES:
        print(f"unknown gate: {phase}", file=sys.stderr)
        return 2
    results: list[dict[str, object]] = []
    for command in GATES[phase]:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        results.append({"command": command, "returncode": completed.returncode})
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        if completed.returncode:
            break
    receipt = {
        "phase": phase,
        "finished_at": datetime.now(UTC).isoformat(),
        "passed": all(item["returncode"] == 0 for item in results),
        "results": results,
    }
    output = Path(".test-receipts") / f"{phase}.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"{'PASS' if receipt['passed'] else 'FAIL'} {phase}; receipt={output}")
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
