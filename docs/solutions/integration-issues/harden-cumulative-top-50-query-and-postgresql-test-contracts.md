---
title: "Harden Cumulative Top-50 Query and PostgreSQL Test Contracts"
date: 2026-07-15
last_updated: 2026-07-17
category: integration-issues
module: maple_inven_monitoring
problem_type: integration_issue
component: testing_framework
symptoms:
  - "Metadata contained every configured board and dozens of Analysis Units, but cumulative rankings and the dashboard selector still exposed only Hero."
  - "The dashboard could return rank 51 and beyond even though it promised a cumulative Top 50."
  - "Production CSV files lacked a UTF-8 BOM, so Windows spreadsheet software could misread Korean text."
  - "A barrier-only concurrency test passed without proving PostgreSQL advisory-lock waiting."
  - "Persistent fixture cleanup could delete fixed-ID state that the test did not create."
root_cause: missing_validation
resolution_type: code_fix
severity: medium
related_components:
  - "database"
  - "service_object"
  - "development_workflow"
  - "tooling"
tags:
  - "cumulative-ranking"
  - "analysis-units"
  - "utf-8-sig"
  - "postgresql-advisory-lock"
  - "test-isolation"
  - "streamlit"
  - "review-regression"
---

# Harden Cumulative Top-50 Query and PostgreSQL Test Contracts

## Problem

The cumulative-ranking slice passed its first test suite, but review found that several claimed guarantees existed only by convention. The dashboard relied on the usual producer setting of 50, the concurrency test inferred database overlap from Python coordination, and fixture cleanup assumed that a known ID implied ownership.

The same pattern later reappeared when production collection expanded beyond the Hero pilot. `latest_post_metrics.csv` contained 2,179 rows across all eight boards and dozens of Analysis Units, while `cumulative_top50.csv` contained exactly 150 Hero rows. The ranking service and dashboard selector still hardcoded `hero`, and otherwise-valid UTF-8 CSV files had no BOM for Windows Excel. The first all-unit ranking fix also changed maintenance queries to slot-only predicates without an index led by the slot.

## Symptoms

- A 51-row regression returned rank 51 from the page query.
- Non-Hero metadata existed, but no Paladin or other Analysis Unit appeared in cumulative rankings or the selector.
- Exported files began with ordinary header bytes instead of the UTF-8-SIG bytes `EF-BB-BF`.
- A barrier put two threads near the refresh call but did not prove that PostgreSQL blocked the second transaction.
- Fixed-ID teardown could remove pre-existing test-database state after a setup collision.
- The UI displayed raw internal keys and emitted a Streamlit deprecation warning.

## What Didn't Work

- Treating `top_n=50` at materialization time as a presentation guarantee. The producer deliberately supports larger values.
- Treating simultaneous Python calls as evidence of a database lock wait.
- Treating fixture identifiers as proof that the current test created the rows.
- Reusing internal query keys as operator-facing labels.
- Treating successful multi-source collection as proof that every downstream consumer was also multi-source.
- Relying on PostgreSQL `COPY ... CSV HEADER` alone for Excel-compatible Korean text.
- Stopping after functional tests passed without auditing index leading columns after broadening a query predicate.

## Solution

Enforce the public page contract at its own query boundary:

```sql
AND ranked.rank <= :row_limit
ORDER BY ranked.rank
LIMIT :row_limit
```

The bound is fixed at 50, and a regression inserts 51 rows and requires ranks 1 through 50 only.

For concurrency, hold the first refresh transaction open, record the second session's backend PID, and require PostgreSQL to show an ungranted advisory lock before releasing the first transaction:

```sql
SELECT EXISTS (
  SELECT 1 FROM pg_locks
  WHERE pid = :pid
    AND locktype = 'advisory'
    AND granted IS FALSE
)
```

Removing the production advisory-lock call makes this test fail, demonstrating that the assertion depends on the real lock rather than timing.

Persistent fixture setup now refuses an existing board before claiming ownership. Destructive cleanup runs only after setup successfully establishes ownership, and a pre-existing sentinel regression proves that collision handling leaves the original row unchanged.

Streamlit selectors keep stable raw keys for queries while `format_func` supplies Korean labels. The table uses the supported `width="stretch"` option.

The ranking refresh now uses the normalized Analysis Unit already stored on every post. Its window and quarantine filters apply to all posts, while `row_number()` continues to partition by `(analysis_unit, metric)`. Replaying a slot deletes and rebuilds that slot across every unit, and detail work items are selected from the distinct ranked union for the same slot.

The dashboard derives its 56 configured choices from `SOURCES` and `JOB_ANALYSIS_UNITS` instead of maintaining a second allowlist. Korean category names remain display-only, and each repeated catch-all is shown as `<직업군> 기타`. Pink Bean and Yeti remain absent because they are not in the canonical source registry.

Every staged production CSV receives an atomic UTF-8 BOM before `SHA256SUMS.txt` is generated:

```bash
printf '\357\273\277' >"$temp"
cat -- "$path" >>"$temp"
mv -f -- "$temp" "$path"
```

Because the all-unit refresh deletes and selects by `as_of_slot_kst`, migration `0005_cumulative_slot_index` adds `cumulative_top_posts_slot_idx (as_of_slot_kst)`. The ORM declares the same index, and a catalog regression verifies its deployed leading column.

## Why This Works

The page independently enforces what it advertises even if another producer stores a larger ranking. Ranking now follows the same Analysis Unit domain as collection, while per-unit SQL partitioning preserves independent Top-N results. Registry-derived labels prevent collection and UI scope from drifting apart. BOM insertion before hashing makes the delivered bytes both Excel-compatible and checksum-verifiable.

PostgreSQL catalog state supplies evidence about the database operations being claimed. Explicit fixture ownership turns teardown from an ID-based assumption into a lifecycle invariant. The slot-leading index matches the widened slot-only predicates, preventing each six-hour replay from scanning the append-only ranking history.

## Prevention

- Add an N+1 regression to every top-N consumer and enforce its own bound.
- Observe database lock state when a test claims blocking; barriers are coordination only.
- Fail closed on persistent fixture collisions and gate cleanup on successful ownership.
- Test localized labels and raw callback values separately.
- Treat deprecation warnings as review findings.
- Trace every scope expansion through collection, normalization, ranking, queueing, dashboard, and export.
- Carry at least one non-default Analysis Unit through materialization and UI regression tests.
- Test published artifact bytes, including BOM and checksum ordering, not only decoded CSV content.
- Audit index leading columns whenever a query predicate changes; keep Alembic, ORM metadata, catalog assertions, and downgrade/upgrade checks aligned.

The final reviewed tree passed all 528 tests. Ruff, Alembic drift, lockfile, Compose configuration, bundled shell syntax, and diff checks passed. An independent reviewer found the missing slot-leading index; after the migration and catalog regression were added, re-review found no remaining Critical, Important, or Minor issues.

## Related Issues

- [Harden Maple Inven Collector Source and Replay Semantics](harden-maple-inven-collector-source-and-replay-semantics.md)
- [Harden the Production CSV Exporter Integration Contract](production-csv-exporter-integration-contract.md)
- [Harden the VPS Production Collector Lifecycle](harden-vps-production-collector-lifecycle.md)
- [Snapshot-Driven, Replayable Monitoring Pipeline](../architecture-patterns/snapshot-driven-replayable-monitoring-pipeline.md)
- [Fail-Closed Local PostgreSQL Test Database Boundaries](../database-issues/fail-closed-local-postgresql-test-database-boundaries.md)
