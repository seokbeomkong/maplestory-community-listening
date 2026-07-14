---
title: "Fail-Closed Local PostgreSQL Test Database Boundaries"
date: 2026-07-14
category: database-issues
module: maple_inven_monitoring
problem_type: database_issue
component: database
symptoms:
  - "Phase 0 could reach Alembic before proving that DATABASE_URL targeted the isolated loopback test database."
  - "Parser differences, routing query parameters, and inherited PG* variables could redirect a nominally safe URL."
  - "Fixture-less or reordered integration tests could enter database-capable code without a preflight."
  - "Prefix and public-schema assumptions could hide ordinary drift or report real partitions as removable tables."
  - "Server-default drift could remain undetected during Alembic comparison."
root_cause: missing_validation
resolution_type: code_fix
severity: high
related_components:
  - "testing_framework"
  - "development_workflow"
  - "tooling"
tags:
  - "postgresql"
  - "alembic"
  - "sqlalchemy"
  - "libpq"
  - "database-safety"
  - "phase-gate"
  - "migration-drift"
  - "fail-closed-validation"
---

# Fail-Closed Local PostgreSQL Test Database Boundaries

## Problem

Local test and migration workflows could acquire a subprocess, Alembic, engine, or connection capability before proving that their effective PostgreSQL configuration targeted the isolated loopback test database. Protection was split across incompatible URL parsers and optional fixtures, omitted libpq environment inputs, and identified partitions by names instead of catalog relationships.

No VPS or production database was modified. Independent reviews found the unsafe paths, and assertion-bomb tests reproduced them without allowing a database-capable call to complete.

## Symptoms

- Unsafe URL variants reached the first mocked Phase 0 command before validation.
- A safe-looking loopback URL plus query overrides or inherited `PG*` variables reached mocked engine boundaries.
- A fixture-less Alembic test body ran before the original requested fixture could validate the target.
- A similarly named ordinary table was hidden as if it were a partition, while a real child partition with a different name appeared as drift.
- A non-`public` default schema made genuine partitions appear removable.
- Changing a server default was invisible until Alembic server-default comparison was enabled.

## What Didn't Work

- Running Alembic later in a four-command gate did not make the gate safe; a guard must run before every capability that can reach the database.
- Validating with `urllib` while SQLAlchemy consumed the original URL created different meanings for encoded names, fragments, and control characters.
- Rejecting only known URL query keys missed libpq's ambient environment inputs.
- Maintaining a list of known dangerous `PG*` variables missed version-specific OAuth controls and could not cover future additions.
- A requested session fixture did not protect tests that requested no fixture or ran in a different order.
- Prefix matching confused a naming convention with a PostgreSQL parent-child relationship.
- The first assertion-bomb harness patched a copied namespace rather than the fixture function's real globals, allowing one promptly terminated TEST-NET connection attempt. No connection or schema operation succeeded.

## Solution

Use one shared validator whose parsing semantics match the SQLAlchemy consumer. Reject malformed raw syntax and decoded controls, then inspect the `URL` returned by `make_url()`:

```python
url = make_url(database_url)

if url.drivername not in {"postgresql", "postgresql+psycopg"}:
    raise UnsafeTestDatabaseUrlError(SAFE_ERROR)
if url.host.casefold() not in {"127.0.0.1", "::1", "localhost"}:
    raise UnsafeTestDatabaseUrlError(SAFE_ERROR)
if url.database != "maple_monitor_test":
    raise UnsafeTestDatabaseUrlError(SAFE_ERROR)
if query_keys & ROUTING_QUERY_KEYS:
    raise UnsafeTestDatabaseUrlError(SAFE_ERROR)
```

The raw checks reject fragments, malformed percent escapes, invalid UTF-8, and raw or decoded control characters. Errors are static and never include the rejected URL, credentials, environment variable name, or value.

Treat the process environment as part of the effective libpq connection configuration. The isolated test boundary rejects every non-empty case-insensitive `PG*` entry rather than maintaining a version-sensitive denylist:

```python
if any(name.casefold().startswith("pg") and value != "" for name, value in environment.items()):
    raise UnsafeTestDatabaseUrlError(SAFE_ENVIRONMENT_ERROR)
```

Empty `PG*` entries and unrelated variables remain allowed. This covers host, service, search-path, credential, TLS, OAuth, mixed-case, and future libpq side channels.

Place the shared validation immediately before every capability acquisition:

- before each of the four Phase 0 subprocesses, so a mid-run environment change stops the next command
- in a function-scoped autouse integration preflight, before every selected test body
- in the session URL fixture and again immediately before engine creation

A failed gate writes a redacted receipt containing no command result when the initial preflight fails, or only results completed before a later environment change.

Replace partition-name filtering with exact PostgreSQL catalog identities. Query `pg_inherits`, `pg_class`, and `pg_namespace` for direct children of `post_metric_snapshots` in `connection.dialect.default_schema_name`; exclude only those exact `(schema, table)` pairs. Complete the catalog-read transaction before Alembic starts its migration transaction, and skip catalog access in offline SQL generation.

Finally, enable server-default comparison and assert the full schema contract through PostgreSQL catalogs and behavior: column types and nullability, ordered primary and foreign keys, allowed and rejected check values, zero metric boundaries, server defaults, sequence ownership, partition key, claim-index order, and clean upgrade/downgrade/re-upgrade.

## Why This Works

Parser-consumer equivalence removes ambiguity: the guard evaluates the same driver, host, database, port, and query representation that SQLAlchemy later uses. Validating the entire effective environment closes inputs that are absent from the URL but still consumed by libpq.

Validation placement is part of the invariant. A correct check that runs after subprocess, fixture body, or engine creation is too late. Revalidating adjacent to each capability makes mutable process state fail closed.

Autouse fixture setup protects focused and reordered tests regardless of explicit fixture dependencies. Session and engine checks remain useful defense in depth at separate consumption boundaries.

Catalog relationships express what a partition is; prefixes express only what it is called. Exact schema-qualified parent-child identities preserve legitimate drift detection under any default schema.

## Prevention

- Keep one shared SQLAlchemy-semantic validator; do not add local string-prefix or alternate-parser checks.
- Treat URL, query, raw encoding, and environment as one effective connection configuration.
- Reject every non-empty `PG*` variable inside the isolated test boundary so new libpq versions fail closed.
- Validate immediately before each subprocess, test body, and engine or connection boundary.
- Use assertion bombs at the actual callable globals and require their call sentinel to remain absent.
- Exercise fixture-less and reordered test paths, not only the normal full-suite order.
- Keep adversarial fixtures for encoded names, fragments, controls, routing keys, DBAPI escape hatches, credentials, OAuth controls, mixed-case variables, and an unknown future `PG*` name.
- Test partition filtering with a non-`public` default schema, a genuinely attached non-prefix child, and an ordinary similarly named table.
- Mutate a server default and require Alembic drift detection, then restore it and require a clean check.
- Require the focused safety suite, migration round trip, offline generation, exact Phase 0 receipt, full integration suite, and independent review before expanding the next phase.

## Related Issues

- [Snapshot-Driven, Replayable Monitoring Pipeline](../architecture-patterns/snapshot-driven-replayable-monitoring-pipeline.md) defines the broader test-gated rollout and deterministic database requirements.
- [Harden Rising Weight Normalization and Configuration Snapshot Immutability](../logic-errors/harden-rising-weight-normalization-and-config-snapshot-immutability.md) applies the same fail-closed boundary-validation pattern to operator configuration.

