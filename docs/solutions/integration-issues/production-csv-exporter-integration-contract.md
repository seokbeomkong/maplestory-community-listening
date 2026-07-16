---
title: "Harden the Production CSV Exporter Integration Contract"
date: 2026-07-15
category: integration-issues
module: production-exporter
problem_type: integration_issue
component: tooling
symptoms:
  - "The deployed Bash helper could not run because its executable mode was not tracked."
  - "PowerShell 5.1 combined multiple ssh/scp command paths into one invalid command name."
  - "Four CSV files could represent different database moments because each export used a separate psql snapshot."
  - "VPS releases grew without a bound, while ZIP failures could leave final-named partial artifacts."
  - "Production acceptance initially covered an older helper protocol rather than the final reviewed bytes."
root_cause: missing_validation
resolution_type: code_fix
severity: high
related_components:
  - "database"
  - "development_workflow"
  - "testing_framework"
tags:
  - "powershell-5-1"
  - "postgresql"
  - "repeatable-read"
  - "atomic-publish"
  - "release-retention"
  - "ssh"
  - "csv-export"
  - "vps-deployment"
---

# Harden the Production CSV Exporter Integration Contract

## Problem

The one-click Windows-to-VPS CSV export crossed several boundaries without preserving one
coherent publication contract. Executability, PowerShell command discovery, database consistency,
remote retention, local artifact atomicity, and the deployed helper all had to agree before an
export could be trusted as a production snapshot.

## Symptoms

- SSH invoked a helper tracked as `100644`, so a mode-preserving installation could fail before
  the export began.
- Windows PowerShell 5.1 found both Windows OpenSSH and a Git-bundled OpenSSH. Accessing `.Source`
  on the resulting collection produced a concatenated, nonexistent executable path.
- Four independent `psql` processes allowed a collector commit to land between CSV exports.
- Every successful download left another permanent VPS release.
- Compression or later-gate failure could leave a production-named folder that appeared complete.
- Earlier fake-command tests used one SSH/SCP application and missed the real Windows behavior.
- Smoke evidence became stale when the wrapper-to-helper protocol changed after deployment.

## What Didn't Work

- A shebang did not replace Git's executable bit or the installed runtime mode.
- Source-text assertions and a single fake executable proved only the happy path, not PowerShell's
  collection-valued command discovery.
- Making each `COPY` read-only did not make four separate sessions one consistent snapshot.
- Atomic staging prevented partial remote releases but did not bound completed-release growth or
  protect a release being transferred from pruning.
- Publishing final names before every gate passed allowed failed output to masquerade as success.
- Reusing an earlier production smoke after changing the remote protocol validated the wrong bytes.

## Solution

### Make execution and command discovery deterministic

Track the helper as executable, install it explicitly as `0700 root:root`, and reduce command
discovery to one application before invoking `.Source`:

```powershell
$sshCommand = Get-Command ssh -CommandType Application -ErrorAction SilentlyContinue |
    Select-Object -First 1
$scpCommand = Get-Command scp -CommandType Application -ErrorAction SilentlyContinue |
    Select-Object -First 1
```

Behavioral tests put two valid SSH and SCP applications on `PATH` and prove that only the first
match runs through the complete verification and download flow. A repository contract also checks
that the helper is stored with mode `100755`.

### Export every CSV from one database snapshot

Run all four `COPY` statements in one `psql` process and one explicit transaction:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

\o /tmp/maple-inven-export-.../latest_post_metrics.csv
COPY (...) TO STDOUT WITH (FORMAT CSV, HEADER TRUE);

\o /tmp/maple-inven-export-.../cumulative_top50.csv
COPY (...) TO STDOUT WITH (FORMAT CSV, HEADER TRUE);

\o /tmp/maple-inven-export-.../collection_runs.csv
COPY (...) TO STDOUT WITH (FORMAT CSV, HEADER TRUE);

\o /tmp/maple-inven-export-.../security_quarantine.csv
COPY (...) TO STDOUT WITH (FORMAT CSV, HEADER TRUE);

\o
COMMIT;
```

The helper writes inside a validated unique container directory, copies the four files into a host
staging directory, generates `SHA256SUMS.txt`, and atomically promotes the completed Export
Release. Cleanup accepts only the exact temporary-path pattern created by the current run.

### Bound retention without pruning active transfers

The remote protocol confines releases to a constant root and validates every release basename and
reconstructed path. `flock` serializes export and prune decisions. A Transfer Lease protects a
published release while SCP operates outside that lock; matching stale leases recover after a
bounded period.

Pruning retains a fixed small number of releases and always protects the current request, the
`latest-download` target, and actively leased releases. It rejects unknown options, paths outside
the release root, symlinks, and malformed candidates before any recursive deletion.

### Publish local artifacts only after every gate succeeds

The wrapper downloads into a GUID-qualified `.partial` directory and accepts exactly four named
CSVs plus `SHA256SUMS.txt`. It rejects missing, extra, nested, duplicate, or mismatched files.

Compression writes to a unique `.partial.zip` while the folder is still partial. Remote retention
must then succeed before the final folder and ZIP names are published. Failure cleanup tracks
ownership explicitly and removes only artifacts created by the current invocation, preserving all
pre-existing exports.

### Redeploy and accept the final protocol

Every helper protocol change invalidates prior production smoke evidence. The final helper was
uploaded through a unique temporary path; local, uploaded, and installed SHA-256 values matched;
installation applied the explicit mode and owner; and the upload was removed.

The exact operator command then produced a verified folder and ZIP. Database counts remained
unchanged, three remote releases remained with no active lease, both services stayed healthy, and
PostgreSQL remained bound only to VPS loopback.

## Why This Works

The exporter applies atomicity at each boundary:

- one repeatable, read-only database snapshot;
- one completed and checksummed remote Export Release;
- one Transfer Lease covering the client download;
- partial local names until validation, compression, and pruning succeed;
- cleanup limited to current-run-owned paths;
- bounded retention guarded by locks, validation, and leases; and
- production acceptance against the exact reviewed and installed bytes.

Individually valid files are therefore published as one coherent, auditable export rather than four
loosely related downloads.

## Prevention

- Review both Git mode and installed mode for every directly invoked script.
- Treat `Get-Command` as collection-valued and test multiple applications in actual `PATH` order.
- Put every file advertised as one snapshot on one connection and one explicit transaction.
- Make production names the last publication step; inject failures at checksum, compression,
  pruning, and rename boundaries and assert no new final or partial artifact remains.
- Constrain recursive deletion with a constant root, strict basename, exact reconstructed path,
  non-symlink target, serialization, and in-flight-consumer protection.
- Keep retention finite and test current, latest, active, stale, malformed, symlink, and concurrent
  candidates.
- Compare local, uploaded, and installed hashes, then run the exact operator command after every
  helper protocol change.
- Record pre/post database counts, run identity, service health, listener exposure, release and
  lease counts, artifact membership, and checksums during acceptance.
- Run focused compatibility tests and a clean isolated full suite; source-text assertions alone do
  not establish cross-platform behavior.

## Related Issues

- [Harden the VPS Production Collector Lifecycle](harden-vps-production-collector-lifecycle.md)
- [Snapshot-Driven, Replayable Monitoring Pipeline](../architecture-patterns/snapshot-driven-replayable-monitoring-pipeline.md)
- [Harden Maple Inven Collector Source and Replay Semantics](harden-maple-inven-collector-source-and-replay-semantics.md)
