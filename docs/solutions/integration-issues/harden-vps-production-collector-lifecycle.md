---
title: "Harden the VPS Production Collector Lifecycle"
date: 2026-07-15
last_updated: 2026-07-17
category: integration-issues
module: production-collector
problem_type: integration_issue
component: background_job
related_components:
  - "database"
  - "tooling"
symptoms:
  - "All live sources failed after page one because valid article links carried a bounded navigational p query that the strict parser rejected."
  - "A Windows-created Git archive converted an LF shell script to CRLF and broke the deployed VPS shebang."
  - "Dirty-worktree tests passed while the committed scheduler omitted an imported runtime module."
  - "A retry or crash could reset the process-local backfill counter and exceed the page budget for one slot."
  - "Failed, partial, or busy incremental sources could still enter backfill and advance historical progress."
root_cause: incomplete_setup
resolution_type: workflow_improvement
severity: high
tags:
  - "production-collector"
  - "vps"
  - "postgresql"
  - "advisory-lock"
  - "durable-budget"
  - "clean-tree"
  - "production-acceptance"
  - "artifact-portability"
---

# Harden the VPS Production Collector Lifecycle

## Problem

The verified one-shot Hero-board collector did not yet have a production-safe execution lifecycle. Promoting the test setup directly would have risked lost collection windows, duplicate upstream crawling, inconsistent container dependencies, ephemeral database storage, and failures that remained invisible while Docker continued to report a running process.

Expanding the pilot to independent multi-source collection exposed a second lifecycle boundary. A passing suite in a dirty worktree did not prove that the reviewed commit contained every imported runtime file. Backfill also bounded pages only inside one Python invocation, so a ranking retry or crash could spend another allowance in the same logical slot. The first replay fix suppressed duplicate fetches but returned an empty success summary, erasing a stored partial outcome.

Live acceptance exposed a third boundary: production-shaped source links and generated deployment artifacts can differ from both fixtures and tracked blobs. Page-two article links carried a legitimate navigational `p` query, while Windows archive conversion changed an otherwise LF-only script to CRLF. Final cross-task review also found that downstream backfill defaulted to every source instead of inheriting each incremental source's terminal eligibility.

## Symptoms

- `_scheduled_cycle` redacted errors but neither retried them nor left a durable terminal status.
- `max_instances=1` prevented overlap only inside one APScheduler process. The existing ranking lock was acquired after the HTTP request.
- The first Docker image installed a manually selected subset and then installed the project with `--no-deps`, which disagreed with project metadata.
- Database reachability was treated as collector health, even though it did not prove that a recent collection succeeded.
- `compose.test.yaml` stored PostgreSQL in `tmpfs`, so it was intentionally disposable.
- `scheduler.py` imported `run_control.py`, but the latter existed only as an untracked file; local imports succeeded while a clean checkout could not start.
- `pages_fetched < budget` reset on every call, allowing a retry after 40 committed backfill pages to request 40 more.
- An `already_succeeded` replay reconstructed backfill as an empty summary and changed a legitimately partial cycle to succeeded.
- The strict link allowlist understood the filtered Hero query but not the public board's bounded page-navigation query.
- The tracked exporter blob and working file were LF-only, yet `git archive` under `core.autocrlf=true` emitted `bash\r\n` in the shebang.
- Backfill's default `SOURCES` argument widened a filtered upstream result back to all sources.

## What Didn't Work

- Treating process-local scheduler throttling as a distributed correctness boundary.
- Locking only final ranking writes after the first external side effect had already occurred.
- Returning a safe error without a persistent identity that the next invocation could resume.
- Using dependency suppression instead of making the collector's package metadata match its runtime role.
- Inferring business health from a live PID or reachable database socket.
- Treating persisted source cursors as a request budget. Cursors preserve accepted progress but do not count upstream attempts across crashes.
- Treating replay as only "do no work." Replay must also reproduce the terminal diagnostics used by status and reporting.
- Running tests only from the current worktree. Untracked Python modules can satisfy imports without being deployable.
- Validating only fixture-shaped URLs instead of the same link variants produced on later live pages.
- Checking repository or working-tree bytes instead of the bytes inside the artifact actually uploaded to production.
- Passing no source list to a downstream function whose default is broader than the upstream eligibility decision.

## Solution

### Claim the slot before fetching

Every run is keyed by `(job_type, scheduled_at_slot_kst)`. A dedicated PostgreSQL connection obtains a session advisory lock derived from that identity before `fetch_list_page()` executes. `run_slots` and `collection_runs` then create or resume one durable lifecycle record.

```python
lock_key = collector_lock_key(JOB_TYPE, slot)
lock_acquired = try_collector_lock(lock_connection, lock_key)
if not lock_acquired:
    return busy_summary

claim = claim_run_slot(...)
if claim.disposition == "already_succeeded":
    return completed_summary
```

A crash releases the session lock automatically. The following invocation resumes a non-succeeded run, while a completed slot exits before another upstream request. Each source uses its own `metadata:<source_key>` identity, so one failed board does not roll back later sources. Snapshot UPSERTs and cumulative-ranking replacement remain replay-safe if a crash occurs after data commit but before the run is marked successful.

### Reserve backfill work durably before fetching

Historical catch-up is a separate `metadata-backfill` run for the aligned slot. Every page allowance is atomically added to persisted run diagnostics before its HTTP request. Reacquiring the slot restores the existing count, so a process crash, ranking failure, or manual replay shares one budget instead of resetting a local counter.

```python
if reserve_page is not None and not reserve_page():
    break
fetch_page(board_id, page)
```

Reservation intentionally precedes fetching. A crash in between may consume an unused allowance, but it cannot create an unaccounted request or exceed the upstream safety limit.

### Replay the stored outcome, not an empty success

The backfill run persists `pages_consumed`, `accepted`, and `failed_sources`. An already-completed replay returns those values without fetching again. Downstream cycle aggregation therefore retains `partial` when any source failed instead of manufacturing a later all-clear result.

### Preserve strictness while accepting live navigation

Canonical article links may carry exactly one bounded decimal `p` query used to return to a public list page. The parser accepts only that narrow shape (or the existing exact Hero category query), rejects duplicates, extra keys, fragments, malformed values, and out-of-range pages, then removes the query from the stored canonical post URL. This fixes live page-two collection without turning arbitrary query data into identity.

### Test the generated deployment artifact

Repository attributes pin every shell script to LF with `*.sh text eol=lf`. The regression test creates a real Git archive and inspects the exporter member's shebang bytes, absence of CRLF, and executable mode. This catches archive-time conversion that blob hashes, working-tree checks, and shell syntax checks alone cannot see.

### Propagate source eligibility explicitly

Backfill receives an explicit tuple built by source key from incremental results. Only `succeeded` and `already_succeeded` sources qualify; `failed`, `partial`, and `busy` sources are omitted, and an empty eligible tuple remains empty rather than falling back to the global registry. Historical progress therefore cannot overtake an incomplete current-range scan.

### Retry only bounded operational failures

`collect_and_rank_with_retries()` uses `collection.max_retries` and the configured minimum and maximum delays. Its retry allowlist covers source, filesystem, and database failures; invalid configuration and unrelated programming errors remain fail-fast. Each failed attempt is recorded with sanitized diagnostics, and success stores the collection and ranking counts.

### Build the image from the frozen collector contract

Collector dependencies remain in the core project set. Dashboard and queue-API dependencies are optional extras, so the VPS role does not install local analytics packages.

```dockerfile
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev && uv pip check
```

The image runs as a non-root user with a read-only filesystem, dropped capabilities, and `no-new-privileges`.

### Measure collector health, not process liveness

`collector-health` requires a recent succeeded `metadata:<source_key>` run. Compose marks the scheduler unhealthy when no source has recently succeeded, and bounded JSON-log rotation prevents silent disk growth. PostgreSQL uses a named volume and binds only to VPS loopback for private tunneling.

## Why This Works

The advisory lock and persistent run ledger solve different failure modes. The lock prevents simultaneous external work, while the ledger survives process death and distinguishes active, failed, partial, and completed slots. Acquiring both before the HTTP request closes the duplicate-crawl gap left by the ranking-only lock.

The same principle applies inside a bounded job. A source cursor says where accepted history resumes; a durable reservation says how much external work the logical slot has already consumed. Persisting both prevents replay from exceeding the budget. Persisting the terminal result envelope makes replay idempotent in meaning as well as side effects.

The retry allowlist restores transient work without hiding invalid configuration. Frozen role-specific dependencies make the built image agree with package metadata. A freshness-based health check exposes the important operational failure: a live container that is no longer collecting.

## Prevention

- Persist a recurring job's deterministic identity before its first external side effect.
- Combine process-local throttling with a cross-process lock tested on independent database connections.
- Skip completed slots, resume failed slots, and keep all downstream writes replay-safe.
- Reserve bounded external work durably before the side effect, and restore the consumed allowance on retry.
- Preserve every terminal field used by aggregation or reporting when returning an already-completed run.
- Carry terminal source eligibility by stable source key into every downstream stage; never let a broad default widen it.
- Retry an explicit transient-error allowlist with bounded attempts; do not retry invalid configuration.
- Define health from recent successful business work rather than process or database liveness alone.
- Build production roles from the committed lockfile and run a dependency consistency check inside the image.
- Keep dashboard, API, browser, OCR, and LLM dependencies outside the collector image unless that role needs them.
- Contract-test persistent storage, private port binding, fail-closed secrets, non-root execution, health checks, and log rotation.
- Verify from the committed snapshot or a clean checkout; a dirty-worktree pass is not deployment evidence.
- Assert new production imports are tracked and included in the installed artifact.
- Exercise live-shaped navigation variants beyond page one while retaining adversarial query tests.
- Inspect generated archive bytes and modes, not only source blobs and working files.
- Test the page budget across ranking retry and crash reacquisition, not only within one function invocation.
- Verify on a clean PostgreSQL database and repeat a live slot to prove that row, budget, outcome, and run identities remain unchanged.

## Verification

- Earlier Hero-board pilot receipt: 456 PostgreSQL-backed tests passed; its production smoke run stored 40 snapshots, materialized 117 cumulative rankings, and repeated the same slot without changing snapshot or run-ledger counts.
- Multi-source lifecycle review receipt: the initial commit was rejected because it relied on an untracked runtime module and an invocation-local backfill budget.
- Regression tests proved reservation-before-fetch, crash reacquisition, a ranking retry capped to one slot budget, and preservation of failed-source diagnostics on replay.
- The final corrected implementation passed all 526 tests; independent task and cross-task re-reviews found no remaining Critical or Important issue.
- Live page-two diagnostics proved all eight sources used the same bounded `p` query shape; the parser fix retained strict rejection of ambiguous query forms.
- The deployed archive showed an LF shebang and the host exporter completed a coherent four-CSV release after the line-ending fix.
- At the next scheduled slot, all eight incremental sources succeeded; Warrior adaptively fetched seven pages to its prior boundary, while the other sources fetched two pages.
- Backfill consumed exactly 40 durable reservations, accepted 1,748 observations, and reported no failed sources. The database contained 2,179 posts and 3,072 snapshots with zero duplicate snapshot identities.
- The checksummed local release and ZIP completed with 2,179 latest-metadata rows across all eight boards, 150 cumulative-ranking rows, 26 run rows, and no quarantined rows.

## Related Issues

- [Harden Maple Inven Collector Source and Replay Semantics](harden-maple-inven-collector-source-and-replay-semantics.md)
- [Harden Cumulative Top-50 Query and PostgreSQL Test Contracts](harden-cumulative-top-50-query-and-postgresql-test-contracts.md)
- [Production CSV Exporter Integration Contract](production-csv-exporter-integration-contract.md)
- [Adaptive Pagination Requires Overlap Before Advancing](../logic-errors/adaptive-pagination-requires-overlap-before-advancing.md)
- [Snapshot-Driven, Replayable Monitoring Pipeline](../architecture-patterns/snapshot-driven-replayable-monitoring-pipeline.md)
