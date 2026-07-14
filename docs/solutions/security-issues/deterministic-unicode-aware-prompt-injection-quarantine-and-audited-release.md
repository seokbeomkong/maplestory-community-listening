---
title: "Deterministic Unicode-Aware Prompt-Injection Quarantine and Audited Release"
date: 2026-07-14
category: security-issues
module: maple_inven_monitoring
problem_type: security_issue
component: service_object
symptoms:
  - "Direct English override text and control-split equivalents could remain below the quarantine threshold."
  - "Cc and Cf characters inserted inside Korean and English anchors could bypass promised rules."
  - "Session-cached rows could hide newer release audits or changed work-item ownership under a lock."
  - "System-tag near misses with long whitespace could trigger quadratic regex backtracking."
root_cause: missing_validation
resolution_type: code_fix
severity: high
related_components:
  - "assistant"
  - "background_job"
  - "database"
  - "testing_framework"
tags:
  - "prompt-injection"
  - "unicode-nfkc"
  - "security-quarantine"
  - "safe-evidence"
  - "audited-release"
  - "sqlalchemy-identity-map"
  - "transaction-safety"
  - "regex-redos"
---

# Deterministic Unicode-Aware Prompt-Injection Quarantine and Audited Release

## Problem

Attacker-controlled forum text needed to be screened before cleaning, embeddings, summaries, clustering, or Codex. The first deterministic scanner could be bypassed with ordinary bounded-gap wording or Unicode controls inserted inside rule anchors. Its release workflow could also reuse stale ORM state, and one system-tag rule allowed hostile input to consume quadratic regex time.

No live-site or VPS incident occurred. Independent reviews found these defects, and controlled tests reproduced them before the pipeline was allowed to expand.

## Symptoms

- `Ignore any previous instructions.` initially produced no finding and risk score zero.
- `Ig\x00nore prior instructions.` produced only the 30-point control finding and stayed below the 70-point quarantine threshold.
- A session that preloaded a pending row could overwrite release audit data committed by another session.
- A cached work item could hide ownership changed by another committed session.
- English and Korean system-tag near misses containing 100,000 spaces exceeded a five-second process timeout.
- An unrelated row occupying a release task key could be mistaken for an idempotent retry without an explicit ownership comparison.

## What Didn't Work

- NFKC normalization canonicalizes full-width and compatibility characters, but it does not remove `Cc` or `Cf` characters inserted inside words.
- Reporting invisible controls separately was insufficient because that finding alone did not reach the quarantine threshold.
- Replacing controls only with spaces preserved separators but broke split words; only removing them could incorrectly join separate tokens. Both detection views were needed.
- The old tag pattern resembled `<\s*/?\s*system`; when no slash followed, two whitespace repetitions explored many partitions of the same long input.
- `FOR UPDATE` did not refresh attributes already present in SQLAlchemy's identity map.
- `ON CONFLICT DO NOTHING` proved key uniqueness, not that an existing work item belonged to this release.

## Solution

Normalize once with NFKC for deterministic scanning and replay identity:

```python
normalized = unicodedata.normalize("NFKC", text)
content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
```

Scan two fixed detection variants:

- a separated variant that replaces control/format characters with spaces
- a collapsed variant that removes them

This catches both controls used as separators and controls inserted inside anchors. The scanner still reports invisible controls independently, while each security rule contributes at most one finding across both variants.

Rules are static, ordered, and use bounded gaps. Evidence comes from the matching sanitized variant, is SHA-256 hashed, clipped, control-escaped, and HTML-escaped. Persisted finding objects contain only the rule ID, score, evidence hash, and escaped evidence. Raw, full, and normalized source text are never stored in the quarantine table.

Group optional syntax with the whitespace it owns to remove ambiguous backtracking:

```python
r"<\s*(?:/\s*)?system"
r"<\s*(?:/\s*)?시스템"
```

Killable child-process tests feed both branches 100,000-space near misses with and without a slash. The old no-slash form exceeded five seconds; the fixed form completed in roughly 0.16–0.18 seconds including interpreter startup.

Quarantine insertion is replay-safe through the unique identity:

```text
(source_kind, source_ref, content_hash)
```

Concurrent replays use `ON CONFLICT DO NOTHING`, return the same quarantine decision, and create one row. Benign content creates neither a quarantine row nor a work item.

Audited release locks and refreshes the current row rather than trusting a session-cached object:

```python
quarantine = session.execute(
    select(SecurityQuarantine)
    .where(SecurityQuarantine.id == quarantine_id)
    .with_for_update()
    .execution_options(populate_existing=True)
).scalar_one_or_none()
```

A pending row receives reviewer, note, and release time once. An identical retry preserves them; different audit data, missing rows, and confirmed rows are rejected. The corresponding `released-analysis:{quarantine_id}:v1` work item is also locked and refreshed, then its kind, canonical payload, and payload hash are compared. An unrelated key collision raises a conflict.

Audit update and enqueue run in a nested savepoint inside the caller-owned transaction. Any ownership conflict rolls back the attempted audit mutation without deleting unrelated work, while an outer caller rollback removes both a new audit and its new work item.

## Why This Works

NFKC, separated detection, and collapsed detection solve different problems: canonical equivalence, separator preservation, and split-anchor reconstruction. Applying fixed rules to all variants while deduplicating per rule makes scores reproducible and prevents repetition-based inflation.

Clipped, escaped, hashed evidence supports human review without turning the quarantine table into a copy of the attacker-controlled source. Downstream analysis uses the canonical source identity only after an audited release creates new work.

The regrouped tag pattern has one whitespace path when no slash exists, so near misses remain linear. A process timeout makes the performance regression killable if a future pattern reintroduces catastrophic behavior.

Row locks serialize writers, and `populate_existing=True` makes the locked database state replace stale identity-map attributes. Explicit work ownership distinguishes a valid retry from a coincidental key conflict. Savepoints keep audit and enqueue atomic without stealing transaction ownership from the caller.

## Prevention

- Keep NFKC-equivalent, full-width, Korean, English, `Cc`, `Cf`, bidi, NUL, newline, tab, and carriage-return fixtures.
- Test both controls inserted inside anchors and controls replacing separators.
- Require one finding per rule, inclusive threshold behavior, deterministic equality, and ordinary gaming-text false-positive guards.
- Persist only source identity, content hash, score, state, timestamps, and exact safe finding keys—never raw or normalized text.
- Review every new regex for nested or adjacent ambiguous unbounded quantifiers and unbounded wildcard gaps.
- Keep killable long-prefix performance tests for every tag-like rule.
- Use real two-session tests with the competing session committed before retrying from a preloaded stale session.
- Refresh locked ORM identities explicitly and compare work-item ownership after conflict-tolerant insertion.
- Test identical release retry, changed-review conflict, unrelated key collision, caller rollback, and savepoint rollback.
- Require scanner, quarantine, integration, migration round-trip, phase-gate, full-suite, and independent-review evidence before downstream semantic work is enabled.

## Related Issues

- [Snapshot-Driven, Replayable Monitoring Pipeline](../architecture-patterns/snapshot-driven-replayable-monitoring-pipeline.md) defines the architecture-level requirement to quarantine hostile content before every semantic transformation.

