# Public Dashboard One-Click Publish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the latest verified VPS export and matching semantic analysis to the public Streamlit dashboard with one PowerShell command.

**Architecture:** A repository-local PowerShell orchestrator composes the existing downloader and analysis CLI, validates their immutable artifacts, stages a minimal public bundle, and pushes an isolated data commit to `main`. A network-free plan mode and fail-closed Git preconditions make the workflow testable and safe to retry.

**Tech Stack:** PowerShell 5.1+, Python 3.12, pytest, Git, Streamlit Community Cloud

## Global Constraints

- Do not publish an incomplete manifest or a manifest whose source name or SHA-256 differs from the ZIP.
- Do not mix existing working-tree changes into a dashboard data commit.
- Require local `main` to exactly match the freshly fetched `origin/main` baseline.
- Publish the exact archive path returned by the downloader, never a directory rescan.
- Do not mutate files, call the network, or invoke Git in `-PlanOnly` mode.
- Stage only `portfolio_data`.

---

### Task 1: Orchestrator contract and implementation

**Files:**
- Create: `scripts/publish-public-dashboard.ps1`
- Create: `tests/unit/test_dashboard_publish_script.py`

**Interfaces:**
- Consumes: `scripts/download-production-data.ps1` and `python -m maple_monitor.cli analyze-export`
- Produces: `publish-public-dashboard.ps1 [-SshHost] [-ExportRoot] [-Remote] [-Branch] [-PlanOnly]`

- [x] **Step 1: Write a failing test for network-free plan output and fail-closed contracts**
- [x] **Step 2: Run the focused test and confirm it fails because the script is absent**
- [x] **Step 3: Implement exact-download selection, synchronized Git baseline, analysis, validation, scoped commit, push, and verified rollback**
- [x] **Step 4: Run the focused test and confirm it passes**

### Task 2: Operator documentation and final verification

**Files:**
- Modify: `docs/portfolio/local-data-refresh.md`
- Create: `docs/superpowers/specs/2026-07-20-public-dashboard-one-click-publish-design.md`

**Interfaces:**
- Consumes: the Task 1 command-line interface
- Produces: copy-ready operating instructions and failure recovery guidance

- [x] **Step 1: Document the single production command and `-PlanOnly` command**
- [x] **Step 2: Document validation gates, rollback, and push retry behavior**
- [x] **Step 3: Run behavioral failure tests, unit, dashboard, and lint verification**
- [ ] **Step 4: Commit and push the verified implementation**
