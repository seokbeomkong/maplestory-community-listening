---
title: "Validate the Export Dashboard Contract and Empty States"
date: 2026-07-17
category: integration-issues
module: export_dashboard
problem_type: integration_issue
component: service_object
symptoms:
  - "Malformed required numeric and datetime values passed archive validation."
  - "Header-only post exports caused dashboard pages to crash."
  - "Job comparisons mixed different evidence windows without disclosing the fallback."
  - "Topic pages omitted the semantic-analysis availability state."
root_cause: missing_validation
resolution_type: code_fix
severity: medium
related_components:
  - "testing_framework"
  - "frontend_stimulus"
tags:
  - "export-validation"
  - "streamlit-dashboard"
  - "data-contract"
  - "empty-state"
  - "time-window"
  - "review-regression"
---

# Validate the Export Dashboard Contract and Empty States

## Problem

The export-backed dashboard trusted structurally plausible CSV and ZIP input too early and assumed
that populated production data would always reach the UI. Review found inputs that could pass the
adapter and then produce a crash or a misleading comparison, even though checksums and column order
were valid.

## Symptoms

- Fractional, negative, oversized, or blank numeric values were not rejected exactly.
- An entirely blank required datetime column could bypass the null check.
- Duplicate or unexpected ZIP members were accepted as long as the required files were present.
- A header-only post export reached timestamp and window code and raised instead of showing an
  explicit empty state.
- Seven-day and sparse-sample fallback cohorts appeared in the same comparison without showing
  their different effective periods.
- Q&A and Tips pages listed engagement but did not state that topic and sentiment evidence was
  absent.
- Partial collection runs appeared in the degraded-run table without their own count.

## What Didn't Work

Reading numeric columns with pandas inference and validating after conversion was too late:

```python
frame = pd.read_csv(source)
frame[column] = frame[column].astype("int64")
```

Inference can discard the source token's exact lexical form before validation. Checking only for
missing ZIP members had a similar weakness: it proved presence, not an exact bundle. A global
semantic warning and a row-level fallback flag also did not ensure that every navigation path
showed its evidence limits.

## Solution

Load CSV fields as strings, validate the source representation, then convert:

```python
frame = pd.read_csv(source, dtype="string")
raw = frame[column].str.strip()

if raw.str.fullmatch(r"-\d+").fillna(False).any():
    raise ExportArchiveError(f"{column} must be non-negative")
if not raw.str.fullmatch(r"\d+").fillna(False).all():
    raise ExportArchiveError(f"{column} must contain integers")

values = raw.map(int)
if values.map(lambda value: value > 2**63 - 1).any():
    raise ExportArchiveError(f"{column} must fit in int64")
```

Required text is checked for null and whitespace-only values. Required datetimes are parsed for
every nonempty table and checked again for missing values after parsing. Archive member names must
be unique and the file set must exactly match the export contract before checksum validation.

At the presentation boundary, the loader stops with an explicit warning when the posts table is
empty, while reusable analysis projections still return typed empty frames. Job comparisons are
split by effective window and fallback cohorts say that a sparse primary sample caused expansion.
Every page that could imply unavailable topic or sentiment analysis renders the semantic-unavailable
state locally. Failed and partial collection runs remain separate counters.

Adversarial data-contract tests and Streamlit AppTests cover fractional and overflowing integers,
negative and blank fields, blank required datetimes, unexpected members, empty posts, fallback
disclosure, and page-specific semantic notices.

## Why This Works

String-first parsing preserves exactly what the exporter supplied until the consumer proves that it
satisfies the contract. Independent lexical, sign, nullability, and storage-bound checks prevent
coercion from weakening that contract. Exact ZIP membership treats an Export Release as one atomic
artifact rather than an arbitrary container of partially related files.

Typed empty projections preserve downstream dataframe contracts, while the page-level stop keeps
timestamp logic away from an evidence-free dataset. Separating effective windows prevents unlike
periods from looking directly comparable, and local semantic notices keep evidence limits visible
regardless of navigation path.

The reviewed fix was verified by 418 unit and dashboard tests, clean Ruff output, and the real
archive loading as 2,179 posts across 51 Analysis Units, 3,948 ranking rows, 26 collection runs, and
four checksum-verified CSV files.

## Prevention

- Preserve CSV source strings until lexical form, sign policy, nullability, and storage bounds have
  all been validated.
- Require exact archive membership, unique member names, complete checksums, and exact column order.
- Include decimals, exponent notation, negatives, overflow, whitespace-only fields, blank required
  datetimes, duplicate ZIP names, and unexpected members in adversarial fixtures.
- Test header-only exports through both analysis functions and full Streamlit pages.
- Never combine fallback cohorts in an unlabeled comparison; expose the effective window and reason
  wherever fallback changes interpretation.
- Render evidence limitations on every page that could otherwise imply unavailable semantic
  analysis.
- Keep success, failure, and partial-run states distinct in domain projections and UI metrics.
- Close implementation review with targeted regressions, re-review, and a fresh full verification.

## Related Issues

- [Harden the Production CSV Exporter Integration Contract](production-csv-exporter-integration-contract.md)
- [Harden Cumulative Top-50 Query and PostgreSQL Test Contracts](harden-cumulative-top-50-query-and-postgresql-test-contracts.md)
- [Snapshot-Driven, Replayable Monitoring Pipeline](../architecture-patterns/snapshot-driven-replayable-monitoring-pipeline.md)
