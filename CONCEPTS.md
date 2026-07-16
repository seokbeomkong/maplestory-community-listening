# Concepts

> Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## Monitoring and Analysis

### Collection Source

An allow-listed public board definition that supplies source identity, board kind, and the Analysis Unit policy used to turn structurally valid list rows into metadata observations.

### Analysis Unit

An independent job, free-board, or information-board scope within which posts are selected, ranked, and compared.

### Collection Slot

An aligned scheduled-time bucket that identifies one replayable collection opportunity; it keys a Metric Snapshot but does not claim when the source was actually fetched.

### High-Water Mark

The newest ordinary post identity from the last complete incremental scan, used as the durable boundary for later scans and never advanced by a partial result.

### Collector Run

The durable execution record for one collection job and Collection Slot, used to resume interrupted work and suppress another upstream fetch after success.

A Collector Run is claimed before external collection begins. Process-local scheduling limits may reduce overlap, but only the slot's cross-process lock and persisted lifecycle determine execution ownership. Replay restores the stored terminal outcome rather than inventing a new summary.

### Backfill Budget

The bounded allowance of historical source-page requests owned by one Collection Slot, distinct from the per-source cursor that records accepted progress.

Each allowance is durably reserved before its external request, so retries and crash recovery share the remaining budget instead of resetting it.

### Source Observation Time

The instant at which source state was fetched, used to order canonical metadata and record factual freshness independently of its Collection Slot or database persistence time.

### Metric Snapshot

A configuration-pinned logical observation of a post's engagement counters for one Collection Slot, used as the factual input to later calculations.

Same-configuration retries monotonically converge counters and Source Observation Time at the same identity; a different Analysis Configuration Version conflicts instead of merging.

### Cumulative Ranking

A rolling-window ordering by accumulated engagement totals, distinct from a Rising Signal that measures recent change.

Each operator-facing Top-N view enforces its advertised bound independently of the materialization that supplies it.

### Rising Signal

A time-windowed momentum result derived from differences between Metric Snapshots, with explicit sample coverage and freshness.

### Analysis Backlog

Collected source material or observations awaiting local derived processing while factual collection continues independently.

### Analysis Freshness

The latest source observation fully reflected in a derived result, used to distinguish a current factual layer from delayed interpretation.

### Security Quarantine

An auditable isolation state for source content suspected of carrying operational instructions or unsafe payloads, preventing semantic processing until an authorized release.

Security Quarantine retains source identity, risk and evidence hashes, and review state rather than the source text. Release preserves the quarantine history with immutable reviewer context and creates one new analysis work item; it does not erase the record or directly authorize model execution.

### Analysis Configuration Version

The stable identity of an immutable, normalized non-secret settings snapshot that produced a collection or derived result, allowing changes to be explained and results to be recomputed.

Configuration versions are opaque identities: they may be compared for equality but never ordered or merged to choose provenance.

## Development Workflow

### Phase Gate

A verified bundle of acceptance checks that must pass before implementation expands into a later phase, leaving a durable receipt of the commands and outcomes.

A production Phase Gate validates the installed artifact and live boundary behavior, not only repository files or fixture-shaped inputs.

### Test Database Preflight

A fail-closed validation that proves the effective database target remains inside the isolated local test scope before any test, migration, subprocess, engine, or connection can acquire database capability.

## Production Export

### Export Release

A coherent, checksummed bundle of production data published from one database snapshot and treated as the indivisible source for one local download.

### Transfer Lease

A temporary ownership marker that protects an Export Release from retention while a client is downloading and validating it.

A Transfer Lease ends only after the client completes its critical publication gates; abandoned leases expire through bounded recovery so retention cannot remain blocked indefinitely.
