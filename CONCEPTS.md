# Concepts

> Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## Monitoring and Analysis

### Analysis Unit

An independent job, free-board, or information-board scope within which posts are selected, ranked, and compared.

### Metric Snapshot

An immutable logical observation of a post's engagement counters for one scheduled collection slot, used as the factual input to later calculations.

### Cumulative Ranking

A rolling-window ordering by accumulated engagement totals, distinct from a Rising Signal that measures recent change.

### Rising Signal

A time-windowed momentum result derived from differences between Metric Snapshots, with explicit sample coverage and freshness.

### Analysis Backlog

Collected source material or observations awaiting local derived processing while factual collection continues independently.

### Analysis Freshness

The latest source observation fully reflected in a derived result, used to distinguish a current factual layer from delayed interpretation.

### Security Quarantine

An auditable isolation state for source content suspected of carrying operational instructions or unsafe payloads, preventing semantic processing until an authorized release.

### Analysis Configuration Version

The stable identity of an immutable, normalized non-secret settings snapshot that produced a collection or derived result, allowing changes to be explained and results to be recomputed.
