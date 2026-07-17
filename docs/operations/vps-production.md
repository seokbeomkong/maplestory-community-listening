# VPS Production Collection

This deployment runs the verified metadata collector against eight allow-listed Maple Inven
sources every six hours. It stores PostgreSQL data in a persistent Docker volume. Text
preprocessing, Codex analysis, and Streamlit remain on the laptop; the VPS never fetches or
exports post bodies, comment text, images, video, or attachments.

The production sources are:

- Warrior (2294)
- Magician (2295)
- Archer (2296)
- Thief (2297)
- Pirate (2298)
- Free (5974)
- Q&A (2300)
- Tips (2304)

## 1. Prepare the VPS

Install Docker Engine, the Docker Compose plugin, Git, and Tailscale on an Ubuntu VPS. Join the
VPS to the same private tailnet as the company laptop. Do not expose ports 5432 or 8501 through
the public firewall.

Clone or copy this repository to `/opt/maple-inven-monitor`, then enter that directory.

## 2. Create production secrets

```bash
cp .env.production.example .env.production
openssl rand -hex 32
chmod 600 .env.production
```

Put the generated value in `POSTGRES_PASSWORD`. Keep `.env.production` only on the VPS and never
commit it. The example uses a URL-safe password because the application constructs a PostgreSQL
URL from this value.

## 3. Migrate and start permanent collection

```bash
docker compose --env-file .env.production -f compose.prod.yaml run --rm migrate
docker compose --env-file .env.production -f compose.prod.yaml up -d --build scheduler
docker compose --env-file .env.production -f compose.prod.yaml ps
docker compose --env-file .env.production -f compose.prod.yaml logs --tail 100 scheduler
```

The scheduler performs one recovery cycle for the latest aligned slot, then schedules collection
at 00:20, 06:20, 12:20, and 18:20 Korea Standard Time. It visits the eight sources sequentially
with concurrency `1` and a randomized 1.5-to-3.0-second request delay. Each source has its own
`metadata:<source_key>` run ledger and advisory lock. Repeating a completed source-slot exits
without another upstream request, and a failed or partial source cannot roll back or block later
sources in the same cycle.

Incremental scanning uses `incremental_min_pages=2`, `incremental_overlap_pages=1`, and
`incremental_max_pages=100`. For an existing source it scans until it finds the prior high-water
boundary, then fetches one overlap page before advancing the boundary. If the prior boundary is
not reached by the 100-page guard, that source is recorded as partial and its boundary does not
advance.

After the incremental attempts, `metadata-backfill` fills the moving 90-day window in round-robin
source order. The `40-page` global allowance is durable per aligned slot: every reserved page is
recorded in the run ledger, so a retry cannot reset and overspend the budget. Each source resumes
with a checkpoint-page overlap, and page or source failures leave its durable cursor unchanged.

Run one additional collection manually when needed:

```bash
docker compose --env-file .env.production -f compose.prod.yaml run --rm scheduler \
  maple-monitor collect-and-rank --now --settings /app/config/settings.yaml
```

Verify that all boards exist and observations are accumulating:

```bash
docker compose --env-file .env.production -f compose.prod.yaml exec postgres \
  sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "select b.id, b.name, count(distinct p.post_id) posts, count(s.*) snapshots from boards b left join posts p on p.board_id=b.id left join post_metric_snapshots s on s.board_id=p.board_id and s.post_id=p.post_id group by b.id,b.name order by b.id;"'
```

Acceptance requires eight board rows and multiple nonempty sources. A temporarily unavailable
source may make the cycle partial only when other sources committed and the failed source did not
advance its incremental boundary or backfill cursor. Inspect the safe per-source diagnostics:

```bash
docker compose --env-file .env.production -f compose.prod.yaml exec postgres \
  sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "select job_type, scheduled_at_slot_kst, status, diagnostics from collection_runs where job_type like '\''metadata%\'' order by scheduled_at_slot_kst desc, job_type limit 40;"'
```

`diagnostics` reports bounded fields such as attempts, pages fetched or consumed, accepted row
counts, boundary state, and failed source keys. It never includes upstream page content. Confirm
that the following duplicate-key query returns no rows:

```bash
docker compose --env-file .env.production -f compose.prod.yaml exec postgres \
  sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "select board_id, post_id, observed_at_slot_kst, count(*) from post_metric_snapshots group by board_id, post_id, observed_at_slot_kst having count(*) > 1;"'
```

`docker compose down` keeps the named database volume. Do not add `-v` unless permanent deletion
of all collected data is intentional.

## 4. Use the database from the laptop

PostgreSQL is bound only to VPS loopback. Open an SSH tunnel over Tailscale from Windows:

```powershell
ssh -N -L 55433:127.0.0.1:5432 maple@VPS-TAILSCALE-HOSTNAME
```

In a second PowerShell window, use the production password from the VPS environment file:

```powershell
$env:DATABASE_URL="postgresql+psycopg://maple_monitor:PRODUCTION_PASSWORD@127.0.0.1:55433/maple_monitor"
uv run streamlit run src/maple_monitor/dashboard/app.py
```

The existing local test database can continue using port 55432; the production tunnel uses
55433 so the two environments cannot be confused.

For a new local environment, install the dashboard extra once before launching Streamlit:

```powershell
uv sync --extra dashboard
```

## 5. Download production CSVs

From the repository root on the laptop, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/download-production-data.ps1
```

The command creates a timestamped folder and matching ZIP under
`C:\Users\tjrqj\Documents\Maplestory\exports`. It exports the current production data with
one repeatable-read, read-only PostgreSQL snapshot, verifies every CSV checksum, and prepares the
ZIP before publishing the final folder and ZIP names. After the verified archive is ready, the
VPS keeps the three most recent completed export releases; releases still being transferred are
temporarily protected from pruning. A failed checksum, ZIP, or prune step leaves no new
production-named artifact on the laptop and does not touch an earlier download. The command
consumes no Codex tokens. The laptop needs to be online only while the command is running and
downloading the files; scheduled collection on the VPS continues independently afterward.

The release contract remains exactly four CSV files plus `SHA256SUMS.txt`:

- `latest_post_metrics.csv` contains every source's latest metrics for each
  `(board_id, post_id)`.
- `cumulative_top50.csv` contains the latest cumulative rankings across all analysis units and
  boards.
- `collection_runs.csv` contains per-source and backfill status plus safe `diagnostics`.
- `security_quarantine.csv` contains the existing quarantine audit metadata.

These are metadata exports; they contain no raw body or comment text.

### Local export dashboard

The export dashboard reads one verified ZIP without connecting to production PostgreSQL. Local
sidecar artifacts hold digest-matched body/comment enrichment and versioned semantic results.

PowerShell (폴더를 지정하면 새 ZIP을 30초 내 자동 감지):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-local-dashboard.ps1
```

POSIX shell:

```bash
export MAPLE_EXPORT_PATH="$(ls -t exports/production-*.zip | head -1)"
uv run streamlit run src/maple_monitor/dashboard/export_app.py
```

The dashboard verifies the archive manifest and CSV schemas before rendering. Do not commit export
archives; they remain local operating data.

## 6. Operations

- Change schedule and ranking values in `config/settings.yaml`, then restart only the scheduler:
  `docker compose --env-file .env.production -f compose.prod.yaml restart scheduler`.
- Check failures with `docker compose --env-file .env.production -f compose.prod.yaml logs scheduler`.
- Docker marks the scheduler unhealthy when no source has a successful collection within 13
  hours. A visible partial cycle remains healthy only when at least one source succeeded. Inspect
  `docker compose ... ps`, scheduler logs, and `collection_runs.csv` diagnostics when this occurs.
- Back up before VPS upgrades or destructive maintenance:

  ```bash
  docker compose --env-file .env.production -f compose.prod.yaml exec -T postgres \
    pg_dump -U maple_monitor -d maple_monitor -Fc > maple-monitor-$(date +%F).dump
  ```

- Keep backups outside the Docker volume and periodically verify restoration into a disposable
  database.
