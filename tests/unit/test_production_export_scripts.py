from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

import pytest


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


def _write_release(
    root: Path,
    *,
    extra_file: bool = False,
    missing_file: str | None = None,
    corrupt_file: str | None = None,
) -> Path:
    release = root / "remote-release"
    release.mkdir()
    for filename in sorted(CSV_FILES):
        (release / filename).write_text(f"name,value\n{filename},1\n", encoding="utf-8")

    checksum_lines = []
    for filename in sorted(CSV_FILES):
        digest = hashlib.sha256((release / filename).read_bytes()).hexdigest()
        checksum_lines.append(f"{digest}  {filename}")
    (release / "SHA256SUMS.txt").write_text(
        "\n".join(checksum_lines) + "\n",
        encoding="ascii",
    )

    if extra_file:
        (release / "unexpected.txt").write_text("not part of the release\n", encoding="utf-8")
    if missing_file is not None:
        (release / missing_file).unlink()
    if corrupt_file is not None:
        with (release / corrupt_file).open("a", encoding="utf-8") as stream:
            stream.write("tampered,2\n")
    return release


def _fake_ssh_environment(
    root: Path,
    release: Path,
    *,
    remote_path: str = "/opt/maple-inven-monitor/exports/releases/20260715-120000-abcd1234",
) -> tuple[dict[str, str], Path, Path]:
    command_dir = root / "commands"
    command_dir.mkdir()
    ssh_marker = root / "ssh-called.txt"
    scp_marker = root / "scp-called.txt"
    scp_helper = root / "fake_scp.py"
    scp_helper.write_text(
        "from pathlib import Path\n"
        "import os\n"
        "import shutil\n"
        "import sys\n"
        "Path(os.environ['FAKE_SCP_MARKER']).write_text('called', encoding='ascii')\n"
        "shutil.copytree(Path(os.environ['FAKE_RELEASE_DIR']), Path(sys.argv[-1]))\n",
        encoding="utf-8",
    )
    (command_dir / "ssh.cmd").write_text(
        "@echo off\r\n"
        "> \"%FAKE_SSH_MARKER%\" echo called\r\n"
        "echo %FAKE_REMOTE_PATH%\r\n"
        "exit /b 0\r\n",
        encoding="ascii",
    )
    (command_dir / "scp.cmd").write_text(
        "@echo off\r\n"
        "\"%FAKE_PYTHON%\" \"%FAKE_SCP_HELPER%\" %*\r\n"
        "exit /b %ERRORLEVEL%\r\n",
        encoding="ascii",
    )

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": str(command_dir),
            "FAKE_PYTHON": sys.executable,
            "FAKE_SCP_HELPER": str(scp_helper),
            "FAKE_RELEASE_DIR": str(release),
            "FAKE_REMOTE_PATH": remote_path,
            "FAKE_SSH_MARKER": str(ssh_marker),
            "FAKE_SCP_MARKER": str(scp_marker),
        }
    )
    return environment, ssh_marker, scp_marker


def _partial_directories(output_root: Path) -> list[Path]:
    return list(output_root.glob("*.partial")) if output_root.exists() else []


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
    assert 'mv -T -- "$staging_dir" "$release_dir"' in script
    assert 'latest_work_dir="$(mktemp -d' in script
    assert 'rm -rf -- "$latest_work_dir"' in script
    assert "latest-download" in script
    assert "printf '%s\\n' \"$release_dir\"" in script

    for filename in CSV_FILES:
        assert filename in script

    lowered = script.lower()
    assert "docker compose" in lowered
    assert "--env-file \"$deploy_root/.env.production\"" in lowered
    assert not re.search(r"(?:cat|source|\.)\s+[^\n]*\.env\.production", lowered)
    assert not re.search(r"docker\s+compose[^\n]*(?:\bup\b|\bdown\b|\brestart\b)", lowered)


def test_bash_helper_is_tracked_as_executable() -> None:
    result = subprocess.run(
        ["git", "ls-files", "--stage", "--", BASH_HELPER.relative_to(REPOSITORY_ROOT)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.split()[0] == "100755"


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


def test_fake_commands_complete_verified_download_and_zip_without_touching_old_exports(
    tmp_path: Path,
) -> None:
    release = _write_release(tmp_path)
    environment, ssh_marker, scp_marker = _fake_ssh_environment(tmp_path, release)
    output_root = tmp_path / "exports"
    old_folder = output_root / "production-20260714-010203"
    old_folder.mkdir(parents=True)
    (old_folder / "sentinel.txt").write_text("preserve me", encoding="utf-8")
    old_zip = output_root / "production-20260714-010203.zip"
    old_zip.write_bytes(b"preserve this zip")

    result = _run_powershell("-OutputRoot", str(output_root), env=environment)

    assert result.returncode == 0, result.stderr
    output_lines = result.stdout.splitlines()
    assert len(output_lines) == 2
    final_folder = Path(output_lines[0])
    final_zip = Path(output_lines[1])
    assert re.fullmatch(r"production-\d{8}-\d{6}", final_folder.name)
    assert final_zip == final_folder.with_suffix(".zip")
    assert {item.name for item in final_folder.iterdir()} == REQUIRED_FILES
    with zipfile.ZipFile(final_zip) as archive:
        assert set(archive.namelist()) == REQUIRED_FILES
        for filename in REQUIRED_FILES:
            assert archive.read(filename) == (release / filename).read_bytes()
    assert ssh_marker.exists()
    assert scp_marker.exists()
    assert (old_folder / "sentinel.txt").read_text(encoding="utf-8") == "preserve me"
    assert old_zip.read_bytes() == b"preserve this zip"
    assert _partial_directories(output_root) == []


def test_rejected_remote_path_never_invokes_scp(tmp_path: Path) -> None:
    release = _write_release(tmp_path)
    environment, ssh_marker, scp_marker = _fake_ssh_environment(
        tmp_path,
        release,
        remote_path="/tmp/not-a-production-release",
    )
    output_root = tmp_path / "exports"

    result = _run_powershell("-OutputRoot", str(output_root), env=environment)

    assert result.returncode != 0
    assert "outside the production release directory" in result.stderr
    assert ssh_marker.exists()
    assert not scp_marker.exists()
    assert _partial_directories(output_root) == []
    assert list(output_root.glob("production-*.zip")) == []


def test_checksum_mismatch_removes_partial_and_never_creates_zip(tmp_path: Path) -> None:
    release = _write_release(tmp_path, corrupt_file="latest_post_metrics.csv")
    environment, _ssh_marker, scp_marker = _fake_ssh_environment(tmp_path, release)
    output_root = tmp_path / "exports"

    result = _run_powershell("-OutputRoot", str(output_root), env=environment)

    assert result.returncode != 0
    assert "Checksum verification failed for latest_post_metrics.csv" in result.stderr
    assert scp_marker.exists()
    assert _partial_directories(output_root) == []
    assert list(output_root.glob("production-*")) == []


@pytest.mark.parametrize(
    ("release_options", "case_name"),
    [
        ({"extra_file": True}, "extra"),
        ({"missing_file": "collection_runs.csv"}, "missing"),
    ],
)
def test_non_exact_release_files_fail_and_remove_partial(
    tmp_path: Path,
    release_options: dict[str, object],
    case_name: str,
) -> None:
    release = _write_release(tmp_path, **release_options)  # type: ignore[arg-type]
    environment, _ssh_marker, scp_marker = _fake_ssh_environment(tmp_path, release)
    output_root = tmp_path / f"exports-{case_name}"

    result = _run_powershell("-OutputRoot", str(output_root), env=environment)

    assert result.returncode != 0
    assert "does not contain exactly the required export files" in result.stderr
    assert scp_marker.exists()
    assert _partial_directories(output_root) == []
    assert list(output_root.glob("production-*")) == []


def test_multiple_ssh_and_scp_applications_invoke_only_the_first_path_match(
    tmp_path: Path,
) -> None:
    release = _write_release(tmp_path)
    environment, first_ssh_marker, first_scp_marker = _fake_ssh_environment(
        tmp_path,
        release,
    )
    second_command_dir = tmp_path / "second-commands"
    second_command_dir.mkdir()
    second_ssh_marker = tmp_path / "second-ssh-called.txt"
    second_scp_marker = tmp_path / "second-scp-called.txt"
    (second_command_dir / "ssh.cmd").write_text(
        "@echo off\r\n"
        "> \"%FAKE_SECOND_SSH_MARKER%\" echo called\r\n"
        "exit /b 91\r\n",
        encoding="ascii",
    )
    (second_command_dir / "scp.cmd").write_text(
        "@echo off\r\n"
        "> \"%FAKE_SECOND_SCP_MARKER%\" echo called\r\n"
        "exit /b 92\r\n",
        encoding="ascii",
    )
    environment["PATH"] = environment["PATH"] + os.pathsep + str(second_command_dir)
    environment["FAKE_SECOND_SSH_MARKER"] = str(second_ssh_marker)
    environment["FAKE_SECOND_SCP_MARKER"] = str(second_scp_marker)
    output_root = tmp_path / "exports"

    result = _run_powershell("-OutputRoot", str(output_root), env=environment)

    assert result.returncode == 0, result.stderr
    assert first_ssh_marker.exists()
    assert first_scp_marker.exists()
    assert not second_ssh_marker.exists()
    assert not second_scp_marker.exists()
