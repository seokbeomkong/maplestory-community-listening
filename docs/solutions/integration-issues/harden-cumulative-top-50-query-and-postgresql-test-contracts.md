---
title: "Harden Cumulative Top-50 Query and PostgreSQL Test Contracts"
date: 2026-07-15
category: integration-issues
module: maple_inven_monitoring
problem_type: integration_issue
component: testing_framework
symptoms:
  - "The dashboard could return rank 51 and beyond even though it promised a cumulative Top 50."
  - "A barrier-only concurrency test passed without proving PostgreSQL advisory-lock waiting."
  - "Persistent fixture cleanup could delete fixed-ID state that the test did not create."
  - "Streamlit exposed internal selector keys and used a deprecated width option."
root_cause: missing_validation
resolution_type: code_fix
severity: medium
related_components:
  - "database"
  - "service_object"
  - "development_workflow"
tags:
  - "cumulative-ranking"
  - "dashboard-row-bound"
  - "postgresql-advisory-lock"
  - "test-isolation"
  - "fixture-ownership"
  - "streamlit"
  - "review-regression"
---

# Harden Cumulative Top-50 Query and PostgreSQL Test Contracts

## Problem

The cumulative-ranking slice passed its first test suite, but review found that several claimed guarantees existed only by convention. The dashboard relied on the usual producer setting of 50, the concurrency test inferred database overlap from Python coordination, and fixture cleanup assumed that a known ID implied ownership.

## Symptoms

- A 51-row regression returned rank 51 from the page query.
- A barrier put two threads near the refresh call but did not prove that PostgreSQL blocked the second transaction.
- Fixed-ID teardown could remove pre-existing test-database state after a setup collision.
- The UI displayed raw internal keys and emitted a Streamlit deprecation warning.

## What Didn't Work

- Treating `top_n=50` at materialization time as a presentation guarantee. The producer deliberately supports larger values.
- Treating simultaneous Python calls as evidence of a database lock wait.
- Treating fixture identifiers as proof that the current test created the rows.
- Reusing internal query keys as operator-facing labels.

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

## Why This Works

The page independently enforces what it advertises even if another producer stores a larger ranking. PostgreSQL catalog state supplies evidence about the database operation being claimed. Explicit fixture ownership turns teardown from an ID-based assumption into a lifecycle invariant. Separating display labels from internal values keeps localization from changing query identities.

## Prevention

- Add an N+1 regression to every top-N consumer and enforce its own bound.
- Observe database lock state when a test claims blocking; barriers are coordination only.
- Fail closed on persistent fixture collisions and gate cleanup on successful ownership.
- Test localized labels and raw callback values separately.
- Treat deprecation warnings as review findings.

The corrected tree passed the Phase 1 gate with 301 unit and 137 integration/dashboard tests, then passed the full 438-test suite. Migration downgrade, upgrade, offline SQL, drift, lint, formatting, and clean-room review checks also passed.

## Related Issues

- [Harden Maple Inven Collector Source and Replay Semantics](harden-maple-inven-collector-source-and-replay-semantics.md)
- [Snapshot-Driven, Replayable Monitoring Pipeline](../architecture-patterns/snapshot-driven-replayable-monitoring-pipeline.md)
- [Fail-Closed Local PostgreSQL Test Database Boundaries](../database-issues/fail-closed-local-postgresql-test-database-boundaries.md)
