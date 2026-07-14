---
title: "Snapshot-Driven, Replayable Monitoring Pipeline"
date: 2026-07-14
category: architecture-patterns
module: maple_inven_monitoring
problem_type: architecture_pattern
component: background_job
severity: high
applies_when:
  - "Designing scheduled monitoring that derives short-window trends from periodically sampled counters"
  - "Splitting always-on collection from intermittently available local analysis"
  - "Requiring crash-safe replay without duplicate observations or derived results"
  - "Processing attacker-controlled content before embeddings, summaries, or Codex analysis"
related_components:
  - "database"
  - "assistant"
  - "development_workflow"
tags:
  - "monitoring-architecture"
  - "metric-snapshots"
  - "idempotent-recovery"
  - "cumulative-rankings"
  - "rising-scores"
  - "configuration-versioning"
  - "prompt-injection-quarantine"
  - "retention-compaction"
---

# Snapshot-Driven, Replayable Monitoring Pipeline

## Context

The Maple Inven monitoring design went through three review rounds. The first version established rolling-window ranking and selective deep collection but assumed one daily run and left offline analysis, trend freshness, recovery identity, configuration, and hostile-input handling underspecified. The next version added the VPS/laptop/Codex split, leases, resource limits, rising formulas, and retention, but still risked mixing cumulative popularity with short-window momentum and assigning derived trend work to the constrained VPS. The approved version corrected those gaps with six-hour source snapshots, separate cumulative and rising products, laptop-local derivation, explicit stale states, versioned operator configuration, and quarantine before any semantic processing.

Only the design requirements and their internal consistency were verified. Runtime services, migrations, controls, and acceptance tests do not yet exist; they remain implementation obligations.

## Guidance

### Preserve source observations before interpretation

Derive collection cadence from the shortest promised analytical window. Store engagement counters with an immutable logical identity such as:

```text
(board_id, post_id, observed_at_slot_kst)
```

A retry may idempotently update the same aligned slot, but a later formula must not rewrite the historical source series. A windowed score requires observations close enough to both boundaries; otherwise return `insufficient_history` instead of interpreting missing history as zero growth.

Prevention rule: every promised time-window metric must define source cadence, boundary tolerance, missing-data behavior, and recomputation inputs.

### Separate cumulative popularity from rising interest

Cumulative totals and short-window changes answer different questions. Give them separate storage, queries, exports, dashboard navigation, and acceptance tests:

- cumulative rankings store rolling-window membership and rank by total views, recommendations, or comments
- rising post results store windowed deltas, acceleration, score components, sample state, freshness, and configuration version
- rising category results aggregate only valid post-level rising results

Do not use a generic trend table or blended “popular now” list that permits lifetime totals and deltas to be compared accidentally.

Prevention rule: metrics with different temporal meaning require different schemas and user-facing labels.

### Place work according to availability and resource boundaries

The VPS is the always-on factual layer: collection, minimal deterministic parsing, durable observations, cumulative ranking, queueing, and private serving. The laptop owns recomputable work: counter deltas, rising scores, OCR, embeddings, clustering, and selective Codex analysis. Immutable VPS snapshots allow a laptop to recalculate results after a weight or algorithm change without recrawling.

When the laptop is offline, collection and cumulative rankings stay current. Rising and text-analysis results retain their last valid values and expose freshness, pending counts, and backlog age. The VPS does not manufacture a partial rising score to hide the outage.

Prevention rule: keep durable facts on the reliable layer and expensive or revisable interpretation on a worker that may disappear without stopping collection.

### Make replay and configuration deterministic

At-least-once work requires deterministic run, task, observation, and result identities; bounded atomic claims; expiring leases; transactional result acknowledgement; unique constraints; and UPSERTs. Page checkpoints advance only with the validated rows from the page. An aligned scheduler slot and advisory lock make duplicate starts converge on the same logical run.

Non-secret controls belong in a validated operator file while credentials remain outside Git. Normalize the settings and attach their hash as a configuration version to every collection run and derived result. An invalid reload keeps the last valid settings. A valid analytical change leaves the previous result labeled with its original version until recomputation succeeds.

Prevention rule: no derived value should exist without enough source and configuration identity to reproduce it.

### Quarantine hostile content before all semantic processing

Every scraped title, body, comment, OCR result, caption, filename, and excerpt is attacker-controlled data. Deterministic Unicode-aware screening runs before cleaning, embeddings, representative selection, summaries, or Codex batching. Suspicious units receive rule IDs, evidence hashes, a risk score, and an auditable quarantine state; they are excluded from downstream analysis until an authenticated human release creates a new work item.

Even accepted text reaches Codex only as de-identified, explicitly delimited data through a tool-free, secret-free, schema-constrained boundary. A model may propose labels but cannot change configuration, enqueue arbitrary work, use a shell or browser, access files, or authorize a database write.

Prevention rule: screening immediately before an LLM is too late because earlier semantic transforms can already propagate attacker instructions.

### Grow the system through test-gated vertical slices

Start with configuration, one migration, one fixture parser, and a health check. Then complete one board from six-hour collection through idempotent storage, a cumulative query, and a minimal dashboard. Add all sources, deep content and quarantine, laptop rising calculations, text analysis, and production operations only after the preceding slice has a passing test receipt.

Prevention rule: a failed phase gate is fixed within that phase; later features do not accumulate on an unverified foundation.

## Why This Matters

Daily-only observations cannot reliably explain a 24-hour change when collection time drifts. A preserved source series makes scoring changes cheap and auditable. Separate cumulative and rising products prevent an old high-volume post from appearing newly popular. Explicit freshness makes laptop or Codex downtime honest instead of silently presenting stale interpretation as current opinion.

Deterministic identities convert crashes and duplicate scheduler starts into harmless replay. Configuration versions explain why a score changed. Bounded retention prevents the VPS from becoming a raw-content archive. Early quarantine and a capability-free model boundary prevent community text from becoming an instruction channel into local tools, credentials, or queue state.

## When to Apply

- An always-on collector feeds an intermittently available analysis machine.
- A product exposes both cumulative popularity and short-window momentum.
- Derived scores may be recalculated after settings or algorithm changes.
- Schedulers or at-least-once queues can repeat work after interruption.
- Source payloads are large or require bounded retention.
- Scraped or user-authored content can reach embeddings, agents, or LLMs.
- The serving host has strict CPU, memory, disk, or bandwidth limits.

A one-off static report may not need the full queue and freshness model, but untrusted-content isolation still applies whenever scraped material reaches a semantic model.

## Examples

### Missing history

```text
Before: one drifting daily row -> assume missing 24-hour delta is zero
After: aligned snapshots -> require valid boundaries -> insufficient_history when absent
```

### Laptop outage

```text
VPS continues canonical snapshots and cumulative rankings
-> rising backlog grows within retention bounds
-> dashboard keeps the last valid result with a stale badge
-> laptop reconnects and processes the oldest eligible leased batches
-> validated results are uploaded idempotently
```

### Configuration change

```text
validate new settings -> derive configuration version v2
-> keep current v1 result labeled v1 and recomputation_pending
-> recompute from immutable snapshots
-> publish validated v2 result without recrawling
```

### Prompt-injection containment

```text
attacker text -> Unicode normalization -> deterministic rule match
-> quarantine with escaped evidence and hash
-> exclude from preprocessing, embeddings, summaries, and Codex
-> retain canonical source identity for audit
```

## Related

- [Maple Inven Monitoring and Analysis Design](../../superpowers/specs/2026-07-14-maple-inven-monitoring-design.md)
