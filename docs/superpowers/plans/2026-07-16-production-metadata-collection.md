# Production Metadata Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Hero-only VPS collector with an eight-source, adaptive metadata collector that fills a moving 90-day window without fixed-page gaps.

**Architecture:** A static allow-listed source registry drives bounded paginated requests and category normalization. Each six-hour cycle commits one independently locked source at a time, scans until its prior high-water boundary plus overlap, then spends a bounded global budget on resumable backfill before refreshing rankings.

**Tech Stack:** Python 3.12, Typer, HTTPX, BeautifulSoup, SQLAlchemy 2, PostgreSQL 16, Alembic, APScheduler, pytest, Docker Compose.

## Global Constraints

- VPS collection stores metadata only and never fetches bodies, comment text, images, video, or attachments.
- Sources are board IDs `2294`, `2295`, `2296`, `2297`, `2298`, `5974`, `2300`, and `2304` only.
- Job categories `팁/정보`, `핑크빈`, and `예티` are excluded after Unicode-normalized exact matching.
- Collection remains sequential with concurrency `1` and a randomized request delay of `1.5` to `3.0` seconds.
- Defaults are `incremental_min_pages=2`, `incremental_overlap_pages=1`, `incremental_max_pages=100`, `backfill_page_budget_per_cycle=40`, `window_days=90`, and `interval_hours=6`.
- Every source-slot is independently idempotent; one failed source cannot roll back or block the other sources.
- Existing response-size, redirect, host, checksum, Docker resource, and safe-diagnostic boundaries remain in force.
- No scheduled VPS action invokes Codex or another LLM.

---

### Task 1: Allow-listed source registry and paginated parsing

**Files:**
- Create: `src/maple_monitor/sources.py`
- Modify: `src/maple_monitor/config.py`
- Modify: `config/settings.yaml`
- Modify: `src/maple_monitor/collection/client.py`
- Modify: `src/maple_monitor/collection/parser.py`
- Modify: `src/maple_monitor/collection/repository.py`
- Modify: `src/maple_monitor/collection/service.py`
- Test: `tests/unit/test_sources.py`
- Test: `tests/unit/test_config.py`
- Test: `tests/unit/test_collection_client.py`
- Test: `tests/unit/test_list_parser.py`
- Test: `tests/integration/test_collection_replay.py`

**Interfaces:**
- Produces: `SourceDefinition`, `SOURCES`, `source_for_board(board_id)`, and `analysis_unit_for(source, category)`.
- Produces: `fetch_list_page(board_id, page=1, *, client=None)` for allow-listed board pages.
- Preserves: `parse_list_page(board_id, html, fetched_at) -> list[PostListItem]` and `collect_board_slot(...)`.

- [ ] **Step 1: Write failing registry, config, client, parser, and repository tests**

Add tests that require the following public contract:

```python
assert [source.board_id for source in SOURCES] == [2294, 2295, 2296, 2297, 2298, 5974, 2300, 2304]
assert source_for_board(5974).key == "free"
assert analysis_unit_for(source_for_board(2294), "히어로") == "hero"
assert analysis_unit_for(source_for_board(2294), "팁/정보") is None
assert analysis_unit_for(source_for_board(2294), "핑크빈") is None
assert analysis_unit_for(source_for_board(2298), "예티") is None
assert analysis_unit_for(source_for_board(5974), "수다") == "free"
assert analysis_unit_for(source_for_board(2300), "아이템") == "qna"
assert analysis_unit_for(source_for_board(2304), "사냥") == "tips"
```

Use an HTTPX mock transport to assert board `5974`, page `3`, requests exactly `https://www.inven.co.kr/board/maple/5974?p=3`; reject page `0`, page `100001`, booleans, unknown boards, redirects, oversized bodies, and response URL changes before returning bytes. The HTTP page validation range is `1..100000`; the independent incremental safety limit remains `100`, while backfill may progress beyond page 100. Extend list-page fixtures so one job row is accepted, the three excluded categories are skipped, and free/Q&A/tips categories map to their fixed analysis units. Extend the integration replay test so `collect_board_slot` creates the correct `boards.name` and `boards.kind` for a non-Hero source.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
uv run pytest tests/unit/test_sources.py tests/unit/test_config.py tests/unit/test_collection_client.py tests/unit/test_list_parser.py tests/integration/test_collection_replay.py -q
```

Expected: failures because the registry, new settings, paginated target, and multi-source normalization do not exist.

- [ ] **Step 3: Implement the minimal registry and multi-source path**

Create an immutable registry with this shape:

```python
@dataclass(frozen=True)
class SourceDefinition:
    key: str
    board_id: int
    name: str
    kind: Literal["job", "free", "info"]
    fixed_analysis_unit: str | None

SOURCES = (
    SourceDefinition("warrior", 2294, "전사", "job", None),
    SourceDefinition("magician", 2295, "마법사", "job", None),
    SourceDefinition("archer", 2296, "궁수", "job", None),
    SourceDefinition("thief", 2297, "도적", "job", None),
    SourceDefinition("pirate", 2298, "해적", "job", None),
    SourceDefinition("free", 5974, "자유 게시판", "free", "free"),
    SourceDefinition("qna", 2300, "질문과 답변", "info", "qna"),
    SourceDefinition("tips", 2304, "팁과 노하우", "info", "tips"),
)
```

Normalize category text with Unicode NFKC plus surrounding whitespace removal. Job analysis units use the following exact stable mapping; unknown job categories fail closed, while the three exclusions return `None`:

```python
JOB_ANALYSIS_UNITS = {
    2294: {
        "히어로": "hero", "팔라딘": "paladin", "다크나이트": "dark_knight",
        "소울마스터": "soul_master", "아란": "aran", "데몬슬레이어": "demon_slayer",
        "미하일": "mihile", "카이저": "kaiser", "데몬어벤져": "demon_avenger",
        "제로": "zero", "블래스터": "blaster", "아델": "adele", "렌": "len",
        "기타": "warrior_other",
    },
    2295: {
        "아크(불독)": "arch_mage_fire_poison", "아크(썬콜)": "arch_mage_ice_lightning",
        "비숍": "bishop", "플레임위자드": "flame_wizard", "에반": "evan",
        "배틀메이지": "battle_mage", "루미너스": "luminous", "키네시스": "kinesis",
        "일리움": "illium", "라라": "lara", "레테": "lete", "기타": "magician_other",
    },
    2296: {
        "보우마스터": "bowmaster", "신궁": "marksman", "윈드브레이커": "wind_archer",
        "와일드헌터": "wild_hunter", "메르세데스": "mercedes",
        "패스파인더": "pathfinder", "카인": "kain", "기타": "archer_other",
    },
    2297: {
        "나이트로드": "night_lord", "섀도어": "shadower", "나이트워커": "night_walker",
        "듀얼블레이드": "dual_blade", "괴도팬텀": "phantom", "카데나": "cadena",
        "호영": "hoyoung", "칼리": "khali", "기타": "thief_other",
    },
    2298: {
        "메카닉": "mechanic", "바이퍼": "buccaneer", "캡틴": "corsair",
        "스트라이커": "thunder_breaker", "캐논슈터": "cannon_shooter",
        "엔젤릭버스터": "angelic_buster", "제논": "xenon", "은월": "shade",
        "아크": "ark", "기타": "pirate_other",
    },
}
```

Non-job sources retain the visible category in `current_category` but use their fixed analysis unit. Replace hard-coded board creation and service validation with registry lookups. Add the four collection controls to `CollectionSettings` with the exact defaults from Global Constraints and validate `min <= max`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass without warnings.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/maple_monitor/sources.py src/maple_monitor/config.py config/settings.yaml src/maple_monitor/collection/client.py src/maple_monitor/collection/parser.py src/maple_monitor/collection/repository.py src/maple_monitor/collection/service.py tests/unit/test_sources.py tests/unit/test_config.py tests/unit/test_collection_client.py tests/unit/test_list_parser.py tests/integration/test_collection_replay.py
git commit -m "feat: support production metadata sources"
```

### Task 2: Adaptive high-water page scanning

**Files:**
- Create: `src/maple_monitor/collection/pagination.py`
- Modify: `src/maple_monitor/collection/repository.py`
- Test: `tests/unit/test_incremental_pagination.py`
- Test: `tests/integration/test_collection_replay.py`

**Interfaces:**
- Consumes: Task 1 `SourceDefinition`, `fetch_list_page`, and `parse_list_page`.
- Produces: `IncrementalScanResult` and `scan_incremental_pages(...)`.
- Produces: `highest_ordinary_post_id(session, board_id) -> int | None`.

- [ ] **Step 1: Write failing adaptive-boundary tests**

Define the desired result:

```python
@dataclass(frozen=True)
class IncrementalScanResult:
    items: tuple[PostListItem, ...]
    pages_fetched: int
    boundary_reached: bool
    high_water_post_id: int | None
    status: Literal["succeeded", "partial"]
```

Tests must prove: a first run fetches exactly two pages; a prior high-water pushed onto page 4 causes five pages to be fetched (four to reach it plus one overlap); an old-ID notice does not establish the boundary; any ordinary ID at or below a deleted prior high-water does; duplicate rows across page edges collapse by `(board_id, post_id)`; and reaching page 100 without the boundary returns `partial` and no advanced high-water.

- [ ] **Step 2: Run pagination tests and verify RED**

```powershell
uv run pytest tests/unit/test_incremental_pagination.py tests/integration/test_collection_replay.py -q
```

Expected: import failure for `maple_monitor.collection.pagination`.

- [ ] **Step 3: Implement minimal adaptive pagination**

Implement a dependency-injected scanner:

```python
def scan_incremental_pages(
    source: SourceDefinition,
    prior_high_water: int | None,
    settings: CollectionSettings,
    *,
    fetch_page: Callable[[int, int], bytes],
    parse_page: Callable[[int, bytes, datetime], list[PostListItem]],
    fetched_at: Callable[[], datetime],
    wait_between_pages: Callable[[], None],
) -> IncrementalScanResult:
    accepted: dict[tuple[int, int], tuple[tuple[int, int, int, int], PostListItem]] = {}
    boundary_page: int | None = None
    greatest_ordinary_id: int | None = None
    pages_fetched = 0

    for page in range(1, settings.incremental_max_pages + 1):
        if page > 1:
            wait_between_pages()
        page_items = parse_page(source.board_id, fetch_page(source.board_id, page), fetched_at())
        pages_fetched = page
        for order, item in enumerate(page_items):
            key = (item.board_id, item.post_id)
            preference = (item.views, item.recommendations, item.comments, page * 10_000 + order)
            if key not in accepted or preference > accepted[key][0]:
                accepted[key] = (preference, item)
            if not item.is_notice and not item.is_ad:
                greatest_ordinary_id = (
                    item.post_id
                    if greatest_ordinary_id is None
                    else max(greatest_ordinary_id, item.post_id)
                )
                if (
                    prior_high_water is not None
                    and boundary_page is None
                    and item.post_id <= prior_high_water
                ):
                    boundary_page = page

        minimum_done = page >= settings.incremental_min_pages
        if prior_high_water is None and minimum_done:
            break
        if (
            boundary_page is not None
            and minimum_done
            and page >= boundary_page + settings.incremental_overlap_pages
        ):
            break

    boundary_reached = prior_high_water is None or boundary_page is not None
    status = "succeeded" if boundary_reached else "partial"
    high_water = greatest_ordinary_id if boundary_reached else prior_high_water
    return IncrementalScanResult(
        items=tuple(value[1] for value in accepted.values()),
        pages_fetched=pages_fetched,
        boundary_reached=boundary_reached,
        high_water_post_id=high_water,
        status=status,
    )
```

Fetch sequentially. For an existing boundary, record the first page containing a non-notice, non-ad ordinary post ID `<= prior_high_water`, then continue through `boundary_page + incremental_overlap_pages` and at least `incremental_min_pages`. For a first run, stop at the minimum. Deduplicate with deterministic preference for the observation having the greatest metrics and latest fetch order. If the maximum arrives before a required boundary, return `partial` and preserve `prior_high_water`; otherwise return the greatest ordinary ID in accepted items.

Implement `highest_ordinary_post_id` as a bounded indexed query on `posts` excluding notices and ads.

- [ ] **Step 4: Run pagination tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/maple_monitor/collection/pagination.py src/maple_monitor/collection/repository.py tests/unit/test_incremental_pagination.py tests/integration/test_collection_replay.py
git commit -m "feat: adapt collection to new post volume"
```

### Task 3: Independent source cycles and resumable 90-day backfill

**Files:**
- Create: `alembic/versions/0004_source_backfill_state.py`
- Modify: `src/maple_monitor/models.py`
- Create: `src/maple_monitor/collection/backfill.py`
- Modify: `src/maple_monitor/ops/scheduler.py`
- Modify: `src/maple_monitor/ops/health.py`
- Modify: `src/maple_monitor/cli.py`
- Test: `tests/integration/test_source_backfill.py`
- Test: `tests/integration/test_run_control.py`
- Test: `tests/unit/test_scheduler.py`
- Test: `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: Task 2 `scan_incremental_pages` and high-water query.
- Produces: `SourceBackfillState` and `run_backfill_budget(...)`.
- Produces: a cycle summary with per-source statuses and total ranking rows.

- [ ] **Step 1: Write failing migration, isolation, replay, and backfill tests**

Require a table with this contract:

```python
class SourceBackfillState(Base):
    __tablename__ = "source_backfill_states"
    source_key: Mapped[str] = mapped_column(Text, primary_key=True)
    next_page: Mapped[int] = mapped_column(Integer)
    checkpoint_post_id: Mapped[int | None] = mapped_column(BigInteger)
    complete: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
```

Tests must prove: each source uses `job_type="metadata:<source_key>"`; failure of one source produces a partial cycle while later sources still commit; replay of the same successful source-slot performs no fetch; a page-guard partial source does not finish succeeded; a 40-page global backfill budget is never exceeded; the next cycle overlaps the checkpoint page; reaching a post older than `slot - 90 days` marks that source complete; and a failed backfill page does not advance state.

- [ ] **Step 2: Run focused orchestration tests and verify RED**

```powershell
uv run pytest tests/integration/test_source_backfill.py tests/integration/test_run_control.py tests/unit/test_scheduler.py tests/unit/test_cli.py -q
```

Expected: missing model, migration, backfill module, and multi-source cycle behavior.

- [ ] **Step 3: Implement source-isolated orchestration and backfill**

Add migration `0004` with `down_revision="0003_cumulative_rankings"`, positive `next_page` check, allow-listed `source_key` check, and updated-at index. Change the scheduler summary to immutable source results:

```python
@dataclass(frozen=True)
class SourceCycleResult:
    source_key: str
    status: Literal["succeeded", "partial", "failed", "busy", "already_succeeded"]
    pages_fetched: int
    accepted: int
    boundary_reached: bool

@dataclass(frozen=True)
class CollectionCycleSummary:
    slot: datetime
    sources: tuple[SourceCycleResult, ...]
    ranking_rows: int
    status: Literal["succeeded", "partial", "failed"]
```

Process `SOURCES` sequentially. Claim, scan, store, and finish each source independently with `metadata:<key>` locks and run slots. Commit only a complete source scan; mark page-guard results partial without advancing the source high-water. Continue after safe collection exceptions and refresh cumulative rankings once after all source attempts.

Run backfill only after incremental attempts. Initialize a source at page 3, resume from `max(1, next_page - 1)`, and advance state transactionally after accepted page metadata. Allocate one page per incomplete source per round until the global budget is exhausted. Stop at the first ordinary row older than the 90-day cutoff. Reuse monotonic post/snapshot upserts and source-specific analysis mapping.

Update CLI JSON to report aggregate source counts without upstream content, and make health accept recent succeeded or partial cycles only when at least one source succeeded.

- [ ] **Step 4: Run orchestration tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 3**

```powershell
git add alembic/versions/0004_source_backfill_state.py src/maple_monitor/models.py src/maple_monitor/collection/backfill.py src/maple_monitor/ops/scheduler.py src/maple_monitor/ops/health.py src/maple_monitor/cli.py tests/integration/test_source_backfill.py tests/integration/test_run_control.py tests/unit/test_scheduler.py tests/unit/test_cli.py
git commit -m "feat: run resilient multi-source collection"
```

### Task 4: Production export, deployment, and acceptance

**Files:**
- Modify: `scripts/export-production-csv.sh`
- Modify: `docs/operations/vps-production.md`
- Modify: `tests/unit/test_production_export_scripts.py`
- Modify: `tests/unit/test_production_deployment.py`

**Interfaces:**
- Preserves: `scripts/download-production-data.ps1` one-command download and its required filenames.
- Extends: exported `collection_runs.csv` diagnostics and all-source metadata rows without adding raw text.

- [ ] **Step 1: Write failing production contract tests**

Assert the export SQL has no Hero-only predicate, includes all boards through the existing joins, and exports the latest snapshot for every `(board_id, post_id)`. Assert the operations document names all eight sources, adaptive boundary behavior, the 40-page backfill budget, partial-source diagnostics, and the production verification query grouped by board.

- [ ] **Step 2: Run production contract tests and verify RED**

```powershell
uv run pytest tests/unit/test_production_export_scripts.py tests/unit/test_production_deployment.py -q
```

Expected: documentation and/or export contract failures for the Hero-only production description.

- [ ] **Step 3: Update export and operations documentation**

Keep the four CSV names and checksum/release protocol unchanged. Ensure `latest_post_metrics.csv` and `cumulative_top50.csv` export all sources, then document these production commands:

```bash
docker compose --env-file .env.production -f compose.prod.yaml run --rm migrate
docker compose --env-file .env.production -f compose.prod.yaml up -d --build scheduler
docker compose --env-file .env.production -f compose.prod.yaml run --rm scheduler \
  maple-monitor collect-and-rank --now --settings /app/config/settings.yaml
docker compose --env-file .env.production -f compose.prod.yaml exec postgres \
  sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "select b.id, b.name, count(distinct p.post_id) posts, count(s.*) snapshots from boards b left join posts p on p.board_id=b.id left join post_metric_snapshots s on s.board_id=p.board_id and s.post_id=p.post_id group by b.id,b.name order by b.id;"'
```

- [ ] **Step 4: Run full local verification**

```powershell
uv run pytest -q
uv run python scripts/gate.py
docker compose -f compose.test.yaml config --quiet
docker compose --env-file .env.production.example -f compose.prod.yaml config --quiet
```

Expected: the full suite and gate pass; both Compose configurations validate.

- [ ] **Step 5: Commit Task 4**

```powershell
git add scripts/export-production-csv.sh docs/operations/vps-production.md tests/unit/test_production_export_scripts.py tests/unit/test_production_deployment.py
git commit -m "docs: operate multi-source metadata collection"
```

- [ ] **Step 6: Deploy and run VPS acceptance**

Upload only the reviewed working tree to `/opt/maple-inven-monitor`, preserve the VPS `.env.production`, create a PostgreSQL-format backup, run migration `0004`, rebuild the scheduler, and execute one manual collection. Verify eight board rows, multiple nonempty sources, no duplicate snapshot keys, bounded Docker memory/CPU, scheduler health, and a fresh local CSV download with valid checksums. If a source is temporarily unavailable, accept a visible partial cycle only when other sources committed and the failed source did not advance its boundary.
