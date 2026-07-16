# One-click Production Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one PowerShell command that exports the current production PostgreSQL data on the VPS, downloads verified CSVs, and creates a timestamped ZIP without Codex.

**Architecture:** A VPS-side Bash helper owns read-only SQL exports and publishes an immutable release directory. A Windows PowerShell wrapper invokes that helper through the existing `maple-vps` SSH alias, downloads the release, validates SHA-256 checksums, and only then creates the final folder and ZIP.

**Tech Stack:** PowerShell 7/Windows PowerShell 5.1, Bash, OpenSSH `ssh`/`scp`, Docker Compose, PostgreSQL `COPY`, pytest.

## Global Constraints

- Use the existing `maple-vps` SSH alias and `/opt/maple-inven-monitor` deployment.
- Never print or download `.env.production` or database credentials.
- PostgreSQL access is read-only and runs inside the existing container.
- Never restart the collector, database, or six-hour scheduler.
- Never overwrite or delete an earlier local export.
- Create the ZIP only after all CSV checksums pass.

---

### Task 1: Export helper and one-click Windows wrapper

**Files:**
- Create: `scripts/export-production-csv.sh`
- Create: `scripts/download-production-data.ps1`
- Create: `tests/unit/test_production_export_scripts.py`

**Interfaces:**
- `export-production-csv.sh` prints exactly one absolute completed release directory on success.
- `download-production-data.ps1 [-SshHost maple-vps] [-OutputRoot PATH] [-PlanOnly]` prints the final folder and ZIP paths.

- [ ] **Step 1: Write failing contract tests**

Create tests that assert both scripts exist, the Bash helper exports the four required CSVs with PostgreSQL `COPY`, generates `SHA256SUMS.txt`, uses a staging directory plus atomic release move, and never reads `.env.production`. Execute the PowerShell wrapper with `-PlanOnly` and assert its JSON contains `maple-vps`, the supplied output root, all required filenames, and a `production-YYYYMMDD-HHMMSS` destination. Assert a host beginning with `-` is rejected.

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/unit/test_production_export_scripts.py -q`

Expected: FAIL because both scripts do not exist.

- [ ] **Step 3: Implement the Bash export helper**

Use `set -euo pipefail`, a `trap` that deletes only its unique staging directory, and the fixed deployment root `/opt/maple-inven-monitor`. Run four `COPY (...) TO STDOUT WITH (FORMAT CSV, HEADER TRUE)` statements through `docker compose ... exec -T postgres psql`. Export latest post metrics, latest cumulative top 50 rows, collection runs, and quarantine entries. Generate checksums from inside the staging directory, move it into `exports/releases/<UTC timestamp>-<random suffix>`, atomically update `exports/latest-download`, and print only the completed absolute path.

- [ ] **Step 4: Implement the PowerShell wrapper**

Use strict mode and terminating errors. Validate `SshHost` with `^[A-Za-z0-9._-]+$`; default `OutputRoot` to `Documents\Maplestory\exports`. `-PlanOnly` returns JSON without network access. Normal execution checks `ssh` and `scp`, invokes the remote helper non-interactively, validates that its returned path is under `/opt/maple-inven-monitor/exports/releases/`, downloads into a unique `.partial` directory, checks the exact required files and every SHA-256 value, renames to `production-YYYYMMDD-HHMMSS`, creates a ZIP, and prints both final paths. On failure, delete only the current `.partial` directory and preserve all earlier exports.

- [ ] **Step 5: Run focused and full tests**

Run: `uv run pytest tests/unit/test_production_export_scripts.py -q`

Expected: PASS.

Run: `uv run pytest -q`

Expected: all existing and new tests PASS.

- [ ] **Step 6: Commit**

Stage only the plan, two scripts, and their test, then commit with `feat: add verified production CSV download`.

### Task 2: VPS installation and production smoke test

**Files:**
- Install from: `scripts/export-production-csv.sh`
- Install to: `/opt/maple-inven-monitor/scripts/export-production-csv.sh`

**Interfaces:**
- Consumes the verified Task 1 scripts and existing `maple-vps` alias.
- Produces a fresh local timestamped folder and ZIP under `C:\Users\tjrqj\Documents\Maplestory\exports`.

- [ ] **Step 1: Install without restarting services**

Upload the Bash helper to a temporary VPS path, verify its SHA-256 against the local file, install it as root with mode `0700`, and remove the temporary upload. Do not run `docker compose up`, `restart`, or `down`.

- [ ] **Step 2: Execute the one-click wrapper**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/download-production-data.ps1`

Expected: exit code 0 and output containing one new folder plus its `.zip` path.

- [ ] **Step 3: Verify production invariants**

Confirm all four CSV checksums, nonzero post/ranking rows, valid ZIP entries, healthy `postgres` and `scheduler` containers, and unchanged collection-run count. Confirm PostgreSQL remains bound only to `127.0.0.1:5432`.

- [ ] **Step 4: Document the operator command**

Add the one-command invocation and output location to `docs/operations/vps-production.md`, including that the laptop is required only while downloading and the operation consumes no Codex tokens.

- [ ] **Step 5: Final verification and commit**

Run focused tests again, `git diff --check`, and verify the production service health. Stage only the helper, wrapper, tests, operations document, and plan, then commit any remaining Task 2 documentation with `docs: document production CSV download`.
