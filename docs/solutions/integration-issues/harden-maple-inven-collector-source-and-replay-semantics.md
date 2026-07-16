---
title: "Harden Maple Inven Collector Source and Replay Semantics"
date: 2026-07-14
last_updated: 2026-07-16
category: integration-issues
module: maple_inven_monitoring
problem_type: integration_issue
component: service_object
symptoms:
  - "Synthetic parser tests passed even though the request URL, fixture topology, and comment markers differed from the production Hero board."
  - "Partial HTTP responses and query- or fragment-bearing article links could be accepted as complete canonical source data."
  - "Bracketed title text could be removed or interpreted as engagement metadata before quarantine scanning."
  - "Scheduled slots, actual fetch times, and configuration provenance were conflated during replay."
  - "Concurrency tests coordinated Python threads without proving PostgreSQL row-lock overlap, while committed tests leaked database state."
root_cause: missing_validation
resolution_type: code_fix
severity: high
related_components:
  - "background_job"
  - "database"
  - "testing_framework"
tags:
  - "maple-inven"
  - "source-contract"
  - "production-shaped-fixture"
  - "fail-closed-parsing"
  - "snapshot-provenance"
  - "idempotent-replay"
  - "postgresql-concurrency"
  - "test-isolation"
---

# Harden Maple Inven Collector Source and Replay Semantics

## Problem

The collector initially agreed with its own synthetic fixtures but not with the public Maple Inven source pages or the database semantics needed for replay. It could silently accept incomplete or structurally ambiguous input, attach counters to the wrong title semantics, and produce metadata or provenance that depended on retry order rather than the observation itself.

When the pilot expanded from one Hero source to a static eight-source registry, a second contract error appeared: the category parser reused a layout-text normalizer that collapsed internal whitespace, even though category metadata allowed only Unicode NFKC normalization plus surrounding trim. Sample-only registry tests also left most source definitions and job-category mappings unprotected from drift.

The durable requirement is stricter: the source response, structural fields, free text, scheduled slot, actual fetch time, configuration identity, and database transaction are separate trust and provenance boundaries. Ambiguity at any boundary must fail closed, while valid retries and concurrent writers must converge without inventing a hybrid observation.

## Symptoms

- The generic warrior-board URL returned multiple job categories while the parser accepted only Hero, so a valid mixed page could fail wholesale.
- The first fixture omitted the author column and production cell classes, placed categories differently, and encoded comments as a numeric title suffix.
- `response.is_success` accepted `206 Partial Content`; a `200` response with `Content-Range` was also treated as complete.
- Query-bearing article links were canonicalized after silently dropping the query. Empty trailing `?` and `#` delimiters also escaped parsed-value checks.
- A title ending in `[2147483647]` could poison the comment metric, while `[질문]` or prompt-like bracket text could disappear before quarantine scanning.
- Snapshot counters from different configuration versions could be combined while `GREATEST` selected an unrelated SHA-256 digest as the row's provenance.
- Snapshot observation time came from database `now()`, and Post freshness used the scheduled slot. Delayed or same-slot retries could therefore preserve stale metadata.
- A pre-call barrier showed only that two Python workers reached a wrapper; it did not prove that PostgreSQL blocked one transaction on the other's row lock.
- Committed integration tests left board state behind, and the first cleanup attempt could delete a pre-existing empty board.
- Category markers containing compatibility or repeated internal whitespace were silently rewritten instead of preserved after NFKC normalization.
- Registry tests remained green when an unasserted source name, kind, fixed analysis unit, or job-category mapping changed.

## What Didn't Work

### Self-consistent synthetic HTML

Sanitizing values is not enough when the fixture's structure was invented. Passing tests only proved that the parser and fixture shared the same assumptions. The corrected fixture is a bounded excerpt of the observed six-column production DOM with IDs, titles, authors, dates, and metrics replaced. The capture had no advertisement row, so the synthetic production-shaped advertisement case is labeled explicitly rather than presented as captured evidence.

### Heuristic parsing at a fail-closed boundary

Loose header matching, searching for a category anywhere in a title cell, and interpreting a trailing bracket as a comment count blurred structural control data with untrusted free text. Skipping a non-Hero row before validating all of its cells also allowed a malformed excluded row to hide page drift.

### Broad HTTP and URL canonicalization helpers

`response.is_success` means any successful 2xx response, not a complete document. Likewise, URL parsing normalizes away the distinction between no delimiter and an empty `?` or `#`. Canonical reconstruction cannot be allowed to erase evidence of an unexpected source shape.

### Ordering opaque configuration hashes

SHA-256 configuration versions are identities, not sortable precedence values. Lexically choosing one hash while independently merging metric maxima can produce a row that corresponds to no collection run.

### Thread coordination presented as database evidence

A barrier immediately before an UPSERT can still be followed by fully sequential SQL execution. It is useful for arranging a test but cannot demonstrate lock waiting, predicate re-evaluation, or convergence under a real race.

### Cleanup without ownership tracking

Deleting any orphaned board assumed the test owned all state it touched. Setup performed before `try/finally` also made failures capable of escaping teardown.

### Generic normalization and sample-only static-contract tests

The parser passed category markers through `_normalized_text()`, a helper designed for layout text:

```python
def _normalized_text(node: Tag) -> str:
    return " ".join(node.get_text(" ", strip=True).split())
```

That split/join is correct for titles and table cells but stronger than the category contract. Applying NFKC afterward could not restore whitespace already collapsed. The tests compounded the gap by checking only board IDs and representative mappings; they proved examples, not the complete ordered source registry or finite job-category map.

## Solution

### Anchor collection to an observed source contract

The owned client constructs an exact page URL only for the static allow-listed board registry and a validated positive page number. It refuses redirects, inherited proxy settings, compressed bodies, and oversized responses. A list response must be an exact `200 OK` with no `Content-Range`:

```python
if response.status_code != httpx.codes.OK or "content-range" in response.headers:
    raise ListPageResponseError("list page response is incomplete")
```

The parser accepts the observed ordered columns and matching direct cell classes:

```text
번호 / num
제목 / tit
글쓴이 / user
등록일 / date
조회 / view
추천 / reco
```

Every data row must validate its complete six-cell topology, canonical article identity, date, and metrics before category filtering. A recognized job category maps to one stable Analysis Unit; explicitly excluded or unmapped job categories are skipped only after structural validation. Non-job sources retain the visible category while using their source's fixed Analysis Unit. Anchorless data rows, duplicate links, extra cells, and drifted classes reject the page.

### Read control data only from structural nodes

The category is exactly one prefix `span.category` directly inside the subject link. Comments are read only from exactly one direct `div.text-wrap > span.con-comment` sibling; blank means zero. Missing, duplicate, malformed, or nested-only markers reject the page.

Only the verified category node is removed from the title. Bracketed questions, numeric suffixes, and malicious-looking text remain title data and reach the existing Unicode-aware quarantine scanner.

Category text has its own narrower normalization path. It reads the structural marker directly, applies NFKC, removes only surrounding whitespace, and preserves internal whitespace:

```python
marker = unicodedata.normalize("NFKC", category_node.get_text()).strip()
match = _CATEGORY_MARKER.fullmatch(marker)
category = match["category"].strip()
```

The regression fixture includes full-width and repeated internal spaces, so a future reintroduction of split/join normalization fails visibly. The static source contracts are also asserted as complete values:

```python
assert tuple(
    (source.key, source.board_id, source.name, source.kind, source.fixed_analysis_unit)
    for source in SOURCES
) == EXPECTED_SOURCES
assert JOB_ANALYSIS_UNITS == EXPECTED_JOB_ANALYSIS_UNITS
```

Representative behavioral tests remain useful, but complete equality is what makes a small finite registry executable documentation. It detects missing, extra, reordered, renamed, or remapped entries.

Article URLs are checked before canonical reconstruction. Literal query or fragment delimiters are rejected, including empty delimiters:

```python
if "?" in raw_href or "#" in raw_href:
    raise InvalidSourcePage("article URL is invalid")
```

The host, scheme, port, board ID, post ID, path, encoding, and length are then validated, and the canonical URL is rebuilt only from validated identities.

### Keep three time meanings separate

One `fetched_at` value is captured at the response boundary and passed through parsing and persistence:

```text
Collection Slot         -> idempotency bucket and snapshot key
Source Observation Time -> relative-date resolution, Post freshness, last_seen_at,
                           and snapshot observed_at_actual
Persistence Time        -> transaction bookkeeping only
```

Post metadata is replaced when the incoming actual observation is later. The bytewise/PostgreSQL `C` rank is used only as a deterministic tie-breaker for exactly equal observation times. Older observations cannot regress canonical metadata.

For a same-configuration snapshot replay, `GREATEST` independently preserves the latest observation time and each monotonic engagement counter. A different configuration at the same post and slot cannot merge:

```text
ON CONFLICT ... DO UPDATE
WHERE existing.config_version = excluded.config_version
```

No returned row raises a fixed, redacted `SnapshotConfigConflict`. The configuration values never appear in the error.

### Keep the transaction caller-owned and atomic

The collection service neither commits nor rolls back. Quarantine records, Post metadata, and the snapshot remain in one caller-owned transaction. A configuration conflict must escape to the caller so that the entire transaction is rolled back; catching the conflict and committing would violate the service contract by preserving partial work.

### Prove the database race at the database boundary

The final concurrency test uses two distinct PostgreSQL backend sessions:

1. Execute the first real Post update and hold its transaction open.
2. Start the second real Post update against the same row.
3. Poll `pg_stat_activity` and `pg_blocking_pids()` until the second backend is active, waiting on `Lock`, and blocked by the first backend PID.
4. Release the first transaction and verify the later actual observation wins.
5. Repeat with the writer order reversed.

This proves row-lock waiting and predicate re-evaluation instead of merely simultaneous Python calls.

### Make committed tests ownership-aware

Database tests record whether the shared board existed before setup. Teardown always deletes the test-owned posts and snapshots, and removes the now-orphaned board only when the test created it. Initial cleanup, committed preseed, barrier installation, worker release, and final cleanup are all protected by teardown-safe `try/finally` scopes.

## Why This Works

The corrected flow preserves one invariant at every boundary:

```text
exact allow-listed URL
  -> exact complete bounded response
  -> production-shaped structural parser
  -> validated typed observations and unmodified free text
  -> quarantine plus deterministic duplicate collapse
  -> Post metadata ordered by actual observation time
  -> snapshot keyed by scheduled slot and pinned configuration
  -> caller commit or whole-transaction rollback
```

The scheduled slot answers "which logical replay bucket is this?" The actual fetch time answers "when was this source state observed?" Database time answers only "when was it persisted?" Keeping those questions separate makes delayed, reversed, and concurrent execution deterministic.

The snapshot primary key makes a same-slot replay idempotent. Per-field maxima remain valid only when the configuration identity matches; an explicit conflict prevents a fabricated cross-configuration row. PostgreSQL evaluates the Post freshness predicate after any required row-lock wait, and the lock-aware test proves that execution path.

Field-specific normalization prevents a layout cleanup policy from silently becoming a metadata mutation policy. NFKC handles compatibility characters, surrounding trim removes structural padding, and the absence of split/join preserves source-visible internal content. Exhaustive equality tests protect the complete finite registry while parser behavior tests protect the transformation semantics.

## Prevention

- Capture external HTML from the production structure, sanitize values separately, and document which rows are synthetic.
- Contract-test exact endpoint, status, completeness headers, ordered columns, cell classes, category placement, comment placement, and article-link cardinality.
- Validate excluded rows completely before applying the category exclusion.
- Preserve free text and remove only verified structural nodes.
- Reject raw query and fragment delimiters before URL canonicalization, including empty `?` and `#`.
- Name and test the scheduled slot, actual observation time, and persistence time as different concepts.
- Treat configuration hashes as equality-only identities; never choose a winner by lexical ordering.
- Exercise replay in both sequential orders and both concurrent writer orders.
- Require database evidence such as `pg_blocking_pids()` before claiming that a concurrency test covers row-lock behavior.
- Keep collection transactions caller-owned, document the rollback contract, and test conflict rollback after partial in-transaction work.
- Make integration cleanup ownership-aware and reproduce suspected leaks with an explicit test order.
- Keep automated HTTP tests offline with bounded sanitized fixtures and mocked transport.
- Define normalization per field; do not reuse a generic helper unless every transformation it performs belongs to that field's contract.
- Test Unicode normalization separately from whitespace collapse using full-width, repeated internal, and surrounding whitespace cases.
- Pin small finite registries and mappings with complete equality assertions, not selected IDs or representative lookups.
- Search docstrings and diagnostics when a pilot scope expands so stale one-source wording cannot outlive the boundary it describes.
- Close every review finding with a failing regression where possible, an exact-tree re-review, the full suite, phase gate, and migration checks.

The expanded source-contract fix produced a review RED of 1 failure with 70 passes, followed by 71 passing affected tests, 120 focused tests, clean Ruff output, and 486 passing repository tests. The independent re-review approved the exact corrected tree with no remaining findings.

## Related Issues

- [Snapshot-Driven, Replayable Monitoring Pipeline](../architecture-patterns/snapshot-driven-replayable-monitoring-pipeline.md) defines the wider VPS/laptop architecture, aligned snapshots, and test-gated rollout.
- [Fail-Closed Local PostgreSQL Test Database Boundaries](../database-issues/fail-closed-local-postgresql-test-database-boundaries.md) documents the same evidence-before-capability principle for local database safety.
- [Harden Rising Weight Normalization and Configuration Snapshot Immutability](../logic-errors/harden-rising-weight-normalization-and-config-snapshot-immutability.md) defines why a configuration version is an opaque identity of one immutable settings snapshot.
- [Deterministic Unicode-Aware Prompt Injection Quarantine and Audited Release](../security-issues/deterministic-unicode-aware-prompt-injection-quarantine-and-audited-release.md) uses NFKC for a different field contract and illustrates why normalization policies must remain purpose-specific.
