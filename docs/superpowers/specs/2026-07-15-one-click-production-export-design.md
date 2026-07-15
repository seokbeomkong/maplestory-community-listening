# One-click production CSV export design

## Goal

Provide a Windows PowerShell command that lets the operator download a fresh,
timestamped CSV snapshot from the production VPS without using Codex tokens.

## Operator interface

Run `scripts/download-production-data.ps1` from the repository. The script uses
the existing `maple-vps` SSH alias and creates both a timestamped folder and ZIP
under `C:\Users\tjrqj\Documents\Maplestory\exports`.

## Data flow

1. Verify non-interactive SSH access to `maple-vps`.
2. On the VPS, export the current database state to a temporary release directory.
3. Produce `latest_post_metrics.csv`, `cumulative_top50.csv`,
   `collection_runs.csv`, `security_quarantine.csv`, and `SHA256SUMS.txt`.
4. Download the complete release into a new timestamped local directory.
5. Verify every downloaded CSV against the server-generated checksums.
6. Create a ZIP only after verification succeeds and print the final paths.

## Safety and failure handling

- The operation is read-only against PostgreSQL.
- Database credentials remain on the VPS and are never printed or downloaded.
- A failed or partial download does not overwrite earlier exports.
- Temporary server export directories use unique timestamps and are removed after
  a successful transfer; the most recent completed export remains available.
- Existing Docker services and the six-hour collection schedule are not restarted.
- Commands fail immediately when SSH, SQL export, transfer, checksum, or ZIP creation fails.

## Verification

Automated tests cover command construction, required export files, timestamped
destinations, checksum failure, and existing-export preservation. A production
smoke test confirms the downloaded CSV row counts and ZIP integrity without
changing collected data.
