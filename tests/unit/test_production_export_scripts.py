from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BASH_HELPER = REPOSITORY_ROOT / "scripts" / "export-production-csv.sh"
POWERSHELL_WRAPPER = REPOSITORY_ROOT / "scripts" / "download-production-data.ps1"
CSV_FILES = {
    "latest_post_metrics.csv",
    "cumulative_top50.csv",
    "collection_runs.csv",
    "security_quarantine.csv",
}
REQUIRED_FILES = CSV_FILES | {"SHA256SUMS.txt"}


def _powershell() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    assert executable is not None, "PowerShell is required to test the one-click wrapper"
    return executable


def _run_powershell(*arguments: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(POWERSHELL_WRAPPER),
            *arguments,
        ],
        cwd=REPOSITORY_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_bash_helper_has_atomic_read_only_export_contract() -> None:
    script = BASH_HELPER.read_text(encoding="utf-8")

    assert "set -euo pipefail" in script
    assert "/opt/maple-inven-monitor" in script
    assert "mktemp -d" in script
    assert "trap cleanup EXIT" in script
    assert "exports/releases" in script or '"$EXPORT_ROOT/releases"' in script
    assert "exec -T postgres" in script
    assert script.count("COPY (") == 4
    assert "TO STDOUT WITH (FORMAT CSV, HEADER TRUE)" in script
    assert "sha256sum" in script
    assert "SHA256SUMS.txt" in script
    assert "mv --" in script
    assert "latest-download" in script
    assert "printf '%s\\n' \"$release_dir\"" in script

    for filename in CSV_FILES:
        assert filename in script

    lowered = script.lower()
    assert "docker compose" in lowered
    assert "--env-file \"$deploy_root/.env.production\"" in lowered
    assert not re.search(r"(?:cat|source|\.)\s+[^\n]*\.env\.production", lowered)
    assert not re.search(r"docker\s+compose[^\n]*(?:\bup\b|\bdown\b|\brestart\b)", lowered)


def test_powershell_wrapper_has_verified_partial_download_contract() -> None:
    script = POWERSHELL_WRAPPER.read_text(encoding="utf-8")

    assert "Set-StrictMode -Version Latest" in script
    assert '$ErrorActionPreference = "Stop"' in script
    assert "^[A-Za-z0-9._-]+$" in script
    assert "BatchMode=yes" in script
    assert "Get-Command" in script
    assert "/opt/maple-inven-monitor/exports/releases/" in script
    assert ".partial" in script
    assert "Get-FileHash" in script
    assert "Compress-Archive" in script
    assert script.index("Get-FileHash") < script.index("Compress-Archive")
    assert "Remove-Item -LiteralPath $partialPath" in script

    for filename in REQUIRED_FILES:
        assert filename in script


def test_plan_only_returns_complete_network_free_json(tmp_path: Path) -> None:
    output_root = tmp_path / "exports"
    environment = os.environ.copy()
    environment["PATH"] = ""

    result = _run_powershell(
        "-PlanOnly",
        "-SshHost",
        "maple-vps",
        "-OutputRoot",
        str(output_root),
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["SshHost"] == "maple-vps"
    assert Path(plan["OutputRoot"]) == output_root
    assert set(plan["RequiredFiles"]) == REQUIRED_FILES
    assert re.fullmatch(r"production-\d{8}-\d{6}", Path(plan["Destination"]).name)
    assert not output_root.exists()


def test_host_starting_with_dash_is_rejected_before_command_discovery() -> None:
    environment = os.environ.copy()
    environment["PATH"] = ""

    result = _run_powershell("-SshHost", "-attacker", env=environment)

    assert result.returncode != 0
    assert "Invalid SSH host" in result.stderr
    assert "ssh command was not found" not in result.stderr
