# VPS Production Collection

This deployment runs the verified MVP collector against the live Hero board every six hours.
It stores PostgreSQL data in a persistent Docker volume. Text preprocessing, Codex analysis,
and Streamlit remain on the laptop.

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

## 3. Start permanent collection

```bash
docker compose --env-file .env.production -f compose.prod.yaml up -d --build
docker compose --env-file .env.production -f compose.prod.yaml ps
docker compose --env-file .env.production -f compose.prod.yaml logs --tail 100 scheduler
```

Startup runs the database migrations, performs one recovery collection for the latest aligned
slot, then schedules collection at 00:20, 06:20, 12:20, and 18:20 Korea Standard Time. Repeating
the same slot reads the completed run ledger and exits without another upstream request. A failed
slot is retried up to `collection.max_retries` times with a bounded randomized delay. A PostgreSQL
advisory lock prevents a second scheduler or manual command from collecting the same slot while
the first is active.

Run one additional collection manually when needed:

```bash
docker compose --env-file .env.production -f compose.prod.yaml run --rm scheduler \
  maple-monitor collect-and-rank --now --settings /app/config/settings.yaml
```

Verify that observations are accumulating:

```bash
docker compose --env-file .env.production -f compose.prod.yaml exec postgres \
  sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "select count(*) as snapshots, max(observed_at_actual) as latest from post_metric_snapshots;"'
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
read-only queries, verifies every CSV checksum before creating the ZIP, and consumes no Codex
tokens. The laptop needs to be online only while the command is running and downloading the
files; scheduled collection on the VPS continues independently afterward.

## 6. Operations

- Change schedule and ranking values in `config/settings.yaml`, then restart only the scheduler:
  `docker compose --env-file .env.production -f compose.prod.yaml restart scheduler`.
- Check failures with `docker compose --env-file .env.production -f compose.prod.yaml logs scheduler`.
- Docker marks the scheduler unhealthy when no successful collection has been recorded for 13
  hours. Inspect `docker compose ... ps` and the scheduler logs when this occurs.
- Back up before VPS upgrades or destructive maintenance:

  ```bash
  docker compose --env-file .env.production -f compose.prod.yaml exec -T postgres \
    pg_dump -U maple_monitor -d maple_monitor -Fc > maple-monitor-$(date +%F).dump
  ```

- Keep backups outside the Docker volume and periodically verify restoration into a disposable
  database.
- This MVP intentionally collects only board 2294, category Hero. Expand the board registry only
  after this production loop has remained stable.
