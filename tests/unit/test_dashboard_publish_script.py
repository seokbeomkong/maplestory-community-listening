from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PUBLISH_SCRIPT = REPOSITORY_ROOT / "scripts" / "publish-public-dashboard.ps1"


def _powershell() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    assert executable is not None, "PowerShell is required to test the publish script"
    return executable


def _git(cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def _write_publish_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    repository = tmp_path / "repository"
    remote = tmp_path / "remote.git"
    helpers = tmp_path / "helpers"
    export_root = tmp_path / "exports"
    (repository / "scripts").mkdir(parents=True)
    (repository / "portfolio_data" / "analysis" / "production-20260701-000000").mkdir(
        parents=True
    )
    helpers.mkdir()
    shutil.copy2(PUBLISH_SCRIPT, repository / "scripts" / PUBLISH_SCRIPT.name)
    (repository / "portfolio_data" / "production-20260701-000000.zip").write_bytes(b"old")
    old_analysis = repository / "portfolio_data" / "analysis" / "production-20260701-000000"
    (old_analysis / "manifest.json").write_text("{}\n", encoding="utf-8")
    (old_analysis / "semantic_posts.csv").write_text("post_id\n", encoding="utf-8")
    (old_analysis / "semantic_comments.csv").write_text("comment_id\n", encoding="utf-8")

    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.name", "Dashboard Publisher Test")
    _git(repository, "config", "user.email", "dashboard-publisher@example.invalid")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "initial public snapshot")
    _git(tmp_path, "init", "--bare", str(remote))
    _git(repository, "remote", "add", "origin", str(remote))
    _git(repository, "push", "-u", "origin", "main")

    downloader = helpers / "fake-download.ps1"
    downloader.write_text(
        "param([string]$SshHost, [string]$OutputRoot)\n"
        "$folder = Join-Path $OutputRoot 'production-20260720-120000'\n"
        "$archive = \"$folder.zip\"\n"
        "New-Item -ItemType Directory -Path $folder -Force | Out-Null\n"
        "[IO.File]::WriteAllBytes($archive, [Text.Encoding]::UTF8.GetBytes('new archive'))\n"
        "Write-Output $folder\n"
        "Write-Output $archive\n",
        encoding="utf-8-sig",
    )
    analyzer = helpers / "fake-analyzer.ps1"
    analyzer.write_text(
        "$archiveIndex = [Array]::IndexOf($args, '--export-path')\n"
        "$analysisIndex = [Array]::IndexOf($args, '--analysis-root')\n"
        "$archive = [IO.Path]::GetFullPath($args[$archiveIndex + 1])\n"
        "$analysisRoot = [IO.Path]::GetFullPath($args[$analysisIndex + 1])\n"
        "$name = [IO.Path]::GetFileNameWithoutExtension($archive)\n"
        "$destination = Join-Path $analysisRoot $name\n"
        "New-Item -ItemType Directory -Path $destination -Force | Out-Null\n"
        "$digest = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()\n"
        "if ($env:FAKE_BAD_HASH -eq '1') { $digest = '0' * 64 }\n"
        "$manifest = [ordered]@{ complete = $true; source_archive = [IO.Path]::GetFileName($archive); source_sha256 = $digest }\n"
        "$manifest | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $destination 'manifest.json')\n"
        "'post_id' | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $destination 'semantic_posts.csv')\n"
        "'comment_id' | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $destination 'semantic_comments.csv')\n"
        "if (-not [string]::IsNullOrWhiteSpace($env:FAKE_STAGE_REPOSITORY)) { 'concurrent' | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $env:FAKE_STAGE_REPOSITORY 'concurrent.txt'); & git -C $env:FAKE_STAGE_REPOSITORY add -- concurrent.txt }\n"
        "if (-not [string]::IsNullOrWhiteSpace($env:FAKE_DELETE_REMOTE)) { Remove-Item -LiteralPath $env:FAKE_DELETE_REMOTE -Recurse -Force }\n"
        "exit 0\n",
        encoding="utf-8-sig",
    )
    return repository, remote, export_root, helpers


def _run_publish(
    repository: Path,
    export_root: Path,
    helpers: Path,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(repository / "scripts" / PUBLISH_SCRIPT.name),
            "-ExportRoot",
            str(export_root),
            "-DownloadScriptPath",
            str(helpers / "fake-download.ps1"),
            "-PythonExecutablePath",
            str(helpers / "fake-analyzer.ps1"),
        ],
        cwd=repository,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_plan_only_describes_the_complete_network_free_publish_flow(tmp_path: Path) -> None:
    export_root = tmp_path / "exports"
    environment = os.environ.copy()
    environment["PATH"] = ""

    result = subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PUBLISH_SCRIPT),
            "-PlanOnly",
            "-ExportRoot",
            str(export_root),
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert Path(plan["RepositoryRoot"]) == REPOSITORY_ROOT
    assert Path(plan["ExportRoot"]) == export_root
    assert Path(plan["PublicDataRoot"]) == REPOSITORY_ROOT / "portfolio_data"
    assert plan["Remote"] == "origin"
    assert plan["Branch"] == "main"
    assert plan["Steps"] == [
        "download",
        "analyze",
        "validate",
        "publish",
        "commit",
        "push",
    ]
    assert not export_root.exists()


def test_publish_script_fails_closed_and_scopes_git_changes() -> None:
    script = PUBLISH_SCRIPT.read_text(encoding="utf-8")

    assert "Set-StrictMode -Version Latest" in script
    assert '$ErrorActionPreference = "Stop"' in script
    assert "download-production-data.ps1" in script
    assert "analyze-export" in script
    assert "semantic_posts.csv" in script
    assert "semantic_comments.csv" in script
    assert "manifest.json" in script
    assert "Get-FileHash" in script
    assert "source_sha256" in script
    assert "complete" in script
    assert "status --porcelain" in script
    assert 'git add -- "portfolio_data"' in script
    assert 'refs/heads/$Branch' in script
    assert "clean -fd -- portfolio_data" in script
    assert "write-tree" in script
    assert "HEAD^{tree}" in script
    assert "commit --only" not in script


def test_publish_uses_exact_download_and_pushes_one_scoped_commit(tmp_path: Path) -> None:
    repository, remote, export_root, helpers = _write_publish_fixture(tmp_path)
    export_root.mkdir()
    (export_root / "production-20991231-235959.zip").write_bytes(b"future stale archive")
    baseline = _git(repository, "rev-parse", "HEAD").stdout.strip()

    result = _run_publish(repository, export_root, helpers)

    assert result.returncode == 0, result.stderr
    published_head = _git(repository, "rev-parse", "HEAD").stdout.strip()
    assert _git(repository, "rev-parse", "HEAD^").stdout.strip() == baseline
    assert _git(repository, "rev-parse", "origin/main").stdout.strip() == published_head
    changed_paths = _git(
        repository,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        "HEAD",
    ).stdout.splitlines()
    assert changed_paths
    assert all(path.startswith("portfolio_data/") for path in changed_paths)
    public_files = _git(
        repository,
        "ls-tree",
        "-r",
        "--name-only",
        "HEAD",
        "portfolio_data",
    ).stdout.splitlines()
    assert "portfolio_data/production-20260720-120000.zip" in public_files
    assert "portfolio_data/production-20991231-235959.zip" not in public_files
    remote_files = _git(
        tmp_path,
        "--git-dir",
        str(remote),
        "ls-tree",
        "-r",
        "--name-only",
        "main",
        "portfolio_data",
    ).stdout.splitlines()
    assert remote_files == public_files


def test_publish_rejects_clean_local_history_ahead_of_remote_before_download(
    tmp_path: Path,
) -> None:
    repository, _remote, export_root, helpers = _write_publish_fixture(tmp_path)
    (repository / "unrelated.txt").write_text("unpublished feature\n", encoding="utf-8")
    _git(repository, "add", "unrelated.txt")
    _git(repository, "commit", "-m", "unpublished feature")

    result = _run_publish(repository, export_root, helpers)

    assert result.returncode != 0
    assert "must exactly match origin/main" in result.stderr
    assert not export_root.exists()


def test_named_operator_branch_at_exact_remote_tip_can_publish(tmp_path: Path) -> None:
    repository, _remote, export_root, helpers = _write_publish_fixture(tmp_path)
    _git(repository, "branch", "-m", "dashboard-operator")

    result = _run_publish(repository, export_root, helpers)

    assert result.returncode == 0, result.stderr
    assert _git(repository, "branch", "--show-current").stdout.strip() == "dashboard-operator"
    assert _git(repository, "rev-parse", "HEAD").stdout.strip() == _git(
        repository, "rev-parse", "origin/main"
    ).stdout.strip()


def test_commit_failure_restores_the_previous_public_snapshot(tmp_path: Path) -> None:
    repository, _remote, export_root, helpers = _write_publish_fixture(tmp_path)
    hook = repository / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 91\n", encoding="ascii")
    baseline = _git(repository, "rev-parse", "HEAD").stdout.strip()

    result = _run_publish(repository, export_root, helpers)

    assert result.returncode != 0
    assert _git(repository, "rev-parse", "HEAD").stdout.strip() == baseline
    assert _git(repository, "status", "--porcelain").stdout == ""
    assert (repository / "portfolio_data" / "production-20260701-000000.zip").exists()
    assert not (repository / "portfolio_data" / "production-20260720-120000.zip").exists()


def test_push_failure_preserves_the_scoped_local_commit_for_retry(tmp_path: Path) -> None:
    repository, remote, export_root, helpers = _write_publish_fixture(tmp_path)
    baseline = _git(repository, "rev-parse", "HEAD").stdout.strip()
    environment = os.environ.copy()
    environment["FAKE_DELETE_REMOTE"] = str(remote)

    result = _run_publish(repository, export_root, helpers, env=environment)

    assert result.returncode != 0
    assert "local publish commit was preserved" in result.stderr
    assert _git(repository, "rev-parse", "HEAD^").stdout.strip() == baseline
    assert _git(repository, "status", "--porcelain").stdout == ""
    changed_paths = _git(
        repository,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        "HEAD",
    ).stdout.splitlines()
    assert changed_paths
    assert all(path.startswith("portfolio_data/") for path in changed_paths)


def test_concurrent_staged_change_cancels_before_public_snapshot_mutation(tmp_path: Path) -> None:
    repository, _remote, export_root, helpers = _write_publish_fixture(tmp_path)
    baseline = _git(repository, "rev-parse", "HEAD").stdout.strip()
    environment = os.environ.copy()
    environment["FAKE_STAGE_REPOSITORY"] = str(repository)

    result = _run_publish(repository, export_root, helpers, env=environment)

    assert result.returncode != 0
    assert "changed while analysis was running" in result.stderr
    assert _git(repository, "rev-parse", "HEAD").stdout.strip() == baseline
    assert "A  concurrent.txt" in _git(repository, "status", "--porcelain").stdout
    assert (repository / "portfolio_data" / "production-20260701-000000.zip").exists()
    assert not (repository / "portfolio_data" / "production-20260720-120000.zip").exists()


def test_manifest_digest_mismatch_is_rejected_before_public_mutation(tmp_path: Path) -> None:
    repository, _remote, export_root, helpers = _write_publish_fixture(tmp_path)
    baseline = _git(repository, "rev-parse", "HEAD").stdout.strip()
    environment = os.environ.copy()
    environment["FAKE_BAD_HASH"] = "1"

    result = _run_publish(repository, export_root, helpers, env=environment)

    assert result.returncode != 0
    assert "source_sha256 does not match" in result.stderr
    assert _git(repository, "rev-parse", "HEAD").stdout.strip() == baseline
    assert _git(repository, "status", "--porcelain").stdout == ""
    assert (repository / "portfolio_data" / "production-20260701-000000.zip").exists()
    assert not (repository / "portfolio_data" / "production-20260720-120000.zip").exists()
