---
title: "Adaptive Pagination Requires Overlap Before Advancing"
date: 2026-07-16
category: logic-errors
module: maple_monitor.collection.pagination
problem_type: logic_error
component: service_object
symptoms:
  - "A prior high-water boundary first found on the final allowed page was reported as a complete scan without fetching the configured overlap page."
  - "The high-water mark advanced even though the incremental scan ended before its overlap postcondition was satisfied."
root_cause: logic_error
resolution_type: code_fix
severity: high
related_components:
  - "background_job"
  - "database"
  - "testing_framework"
tags:
  - "adaptive-pagination"
  - "incremental-scan"
  - "high-water-mark"
  - "overlap-pages"
  - "page-limit"
---

# Adaptive Pagination Requires Overlap Before Advancing

## Problem

An adaptive incremental scan has two separate completion conditions: it must discover the prior high-water boundary and then fetch every configured overlap page after that boundary. The first implementation treated boundary discovery as success by itself. If the boundary was first found on the maximum allowed page, the scan could not fetch the overlap page but still returned `succeeded` and advanced its durable checkpoint.

That false success creates a permanent gap risk. Later scans start from the newly advanced high-water mark even though the preceding scan never completed the safety overlap intended to absorb ordering changes and page-boundary movement.

## Root Cause

The success predicate represented discovery rather than the full postcondition:

```python
boundary_reached = prior_high_water is None or boundary_page is not None
```

The page-limit guard therefore became fail-open at exactly the edge where the boundary was found but the overlap could not be completed.

## Resolution

Completion now requires both boundary discovery and enough fetched pages to cover the configured overlap:

```python
boundary_reached = prior_high_water is None or (
    boundary_page is not None
    and pages_fetched >= boundary_page + settings.incremental_overlap_pages
)
status = "succeeded" if boundary_reached else "partial"
high_water = greatest_ordinary_id if boundary_reached else prior_high_water
```

A partial scan preserves the prior high-water mark. The regression test places the boundary on page 100 with one required overlap page and a 100-page limit, then asserts the invariants together: 100 pages fetched, `boundary_reached` false, status `partial`, and the prior high-water mark unchanged.

## Prevention Rules

- Express scan success as all required postconditions, not the first milestone discovered during the scan.
- Treat a safety page limit as fail-closed when it prevents completion.
- Never advance a durable checkpoint from a partial result.
- Test both boundary-not-found and boundary-found-at-the-limit cases.
- Assert status, checkpoint, page count, and completion flag together so they cannot drift independently.

## Related

- [Snapshot-Driven, Replayable Monitoring Pipeline](../architecture-patterns/snapshot-driven-replayable-monitoring-pipeline.md)
- [Harden Maple Inven Collector Source and Replay Semantics](../integration-issues/harden-maple-inven-collector-source-and-replay-semantics.md)
