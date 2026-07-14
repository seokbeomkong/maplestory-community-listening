---
title: "Harden Rising Weight Normalization and Configuration Snapshot Immutability"
date: 2026-07-14
category: logic-errors
module: maple_inven_monitoring
problem_type: logic_error
component: service_object
symptoms:
  - "Non-finite YAML weights could pass validation and replace the last-valid configuration."
  - "Very large finite weights could overflow the denominator and normalize to all-zero weights."
  - "A frozen settings snapshot allowed in-place window mutation without changing its configuration version."
root_cause: missing_validation
resolution_type: code_fix
severity: medium
related_components:
  - "background_job"
  - "testing_framework"
tags:
  - "configuration-validation"
  - "floating-point"
  - "overflow-safe-normalization"
  - "immutable-snapshots"
  - "reload-safety"
  - "config-versioning"
  - "pydantic"
  - "regression-testing"
---

# Harden Rising Weight Normalization and Configuration Snapshot Immutability

## Problem

The operator configuration accepted non-finite rising-score weights and normalized large finite weights by summing them directly. This could publish invalid normalized values and allow a bad reload to replace the last-valid settings. The supposedly frozen settings also contained a mutable window list, so its contents could change after its configuration version had been calculated.

## Symptoms

- Reloading YAML containing an infinite weight succeeded instead of preserving the previous settings.
- Two finite weights near the floating-point maximum overflowed their raw sum and normalized to values totaling zero.
- Appending to the loaded window list succeeded even though the settings model was frozen.
- The configuration version stayed unchanged after that in-place mutation.
- Ordinary default-value tests remained green because normal-sized values did not exercise these boundaries.

## What Didn't Work

- A non-negative field constraint was treated as a finiteness guarantee. It does not reject positive infinity unless non-finite values are explicitly disabled.
- Checking a raw total for zero was treated as sufficient validation. The total can overflow even when every input is finite.
- Freezing the Pydantic model was treated as deep immutability. Field reassignment is blocked, but a nested list can still be mutated.

These were failed implementation assumptions rather than investigative dead ends. Focused regression tests reproduced each one before the fix.

## Solution

Reject non-finite inputs, validate that at least one weight is positive without summing the raw values, scale by the maximum weight before calculating the denominator, and convert operator-provided window lists to tuples.

Before:

```python
windows_hours: list[int] = Field(min_length=1)
recommendation_weight: float = Field(ge=0)

total = recommendation_weight + comment_weight + view_weight
normalized = recommendation_weight / total
```

After:

```python
windows_hours: tuple[int, ...] = Field(min_length=1)
recommendation_weight: float = Field(ge=0, allow_inf_nan=False)

scale = max(recommendation_weight, comment_weight, view_weight)
scaled = (
    recommendation_weight / scale,
    comment_weight / scale,
    view_weight / scale,
)
total = sum(scaled)
normalized = tuple(weight / total for weight in scaled)
```

With finite non-negative inputs and at least one positive value, every scaled intermediate lies between zero and one and at least one equals one. Their sum is therefore finite and positive. Invalid reloads fail during candidate validation, leaving the exact previous settings object in place and recording the error.

Regression tests cover infinite input, very large finite input, all-zero input, failed-reload object identity, finite unit-sum output, and attempted in-place window mutation. The complete Task 1 suite, code checks, phase gate, and independent re-review passed after the change.

## Why This Works

Explicit finiteness validation closes the NaN and infinity paths before arithmetic. Maximum scaling prevents a sum of individually valid floats from overflowing, while preserving their ratios. An immutable tuple closes the shallow-freezing gap, so the configuration version continues to identify the exact settings snapshot held in memory.

Together these guarantees make last-valid reload behavior meaningful: a candidate is either a complete, reproducible settings snapshot or it is rejected without changing the active one.

## Prevention

- Every configuration float used in arithmetic explicitly rejects NaN and infinity; range constraints alone are insufficient.
- Potentially large weights are normalized through bounded intermediates rather than a raw sum.
- Versioned settings snapshots contain only immutable nested values.
- Reload-failure tests assert object identity as well as an error result.
- Numerical tests assert every result is finite and the normalized values sum to one.
- Boundary fixtures include non-finite values, extreme finite values, all-zero values, and mutable YAML collection inputs.
- Any change to validation or serialization reruns the phase gate before later implementation work starts.

## Related Issues

- [Snapshot-Driven, Replayable Monitoring Pipeline](../architecture-patterns/snapshot-driven-replayable-monitoring-pipeline.md) defines the architecture-level requirement for validated, versioned settings and last-valid reload behavior.

