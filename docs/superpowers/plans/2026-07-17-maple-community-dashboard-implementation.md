# Maple Community Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a private Streamlit dashboard that reads a verified production ZIP and presents factual overview, job, free, Q&A, tips, and operations views without fabricating unavailable semantic analysis.

**Architecture:** Preserve the existing database-backed cumulative page and add a separate export-backed entry point. A pure archive adapter validates and types the four CSVs, pure analysis functions derive windows and summaries, and direct Streamlit page scripts render those projections through top navigation.

**Tech Stack:** Python 3.12, pandas 2.x, Streamlit 1.57, pytest, Streamlit AppTest

## Global Constraints

- Keep popularity separate from sentiment and author position separate from comment reaction.
- Default windows are free 24 hours, jobs and Q&A 7 days, tips 30 days; jobs may fall back to 30 days with a visible reason.
- Current metadata must not be labeled as topic, sentiment, agreement, or controversy analysis.
- Every view shows source period, sample size, and factual freshness.
- Use native Streamlit components and `.streamlit/config.toml`; add no custom HTML or CSS.
- Preserve the existing database-backed cumulative dashboard.
- Use Korean sentence-case labels and a restrained light editorial palette.

---

### Task 1: Verified export adapter

**Files:**
- Create: `src/maple_monitor/dashboard/export_data.py`
- Create: `tests/dashboard/test_export_data.py`

**Interfaces:**
- Produces: `ExportArchiveError`, `ExportBundle`, `load_export_archive(path: Path) -> ExportBundle`
- `ExportBundle` contains `posts`, `rankings`, `runs`, `quarantine`, `checksums`, and `source_path`.

- [ ] **Step 1: Write failing tests for valid archives, checksum mismatch, missing members, schema drift, numeric typing, and unsafe source URLs**

```python
def test_load_export_archive_validates_and_types_all_tables(export_zip: Path) -> None:
    bundle = load_export_archive(export_zip)
    assert bundle.posts["views"].dtype.kind in "iu"
    assert bundle.posts["published_at"].dt.tz is not None
    assert bundle.checksums["latest_post_metrics.csv"] is True


def test_load_export_archive_rejects_checksum_mismatch(corrupt_export_zip: Path) -> None:
    with pytest.raises(ExportArchiveError, match="checksum"):
        load_export_archive(corrupt_export_zip)
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `uv run pytest tests/dashboard/test_export_data.py -q`

Expected: FAIL because `maple_monitor.dashboard.export_data` does not exist.

- [ ] **Step 3: Implement the minimal adapter**

```python
@dataclass(frozen=True)
class ExportBundle:
    posts: pd.DataFrame
    rankings: pd.DataFrame
    runs: pd.DataFrame
    quarantine: pd.DataFrame
    checksums: Mapping[str, bool]
    source_path: Path


def load_export_archive(path: Path) -> ExportBundle:
    raw = path.read_bytes()
    with ZipFile(BytesIO(raw)) as archive:
        checksums = _verify_members(archive)
        posts = _read_typed_csv(archive, "latest_post_metrics.csv")
        rankings = _read_typed_csv(archive, "cumulative_top50.csv")
        runs = _read_typed_csv(archive, "collection_runs.csv")
        quarantine = _read_typed_csv(archive, "security_quarantine.csv")
    return ExportBundle(posts, rankings, runs, quarantine, checksums, path)
```

Validate exact required members and required columns, parse KST timestamps, cast counters to integers, reject duplicate expected keys, and blank non-HTTPS or non-Inven source links before presentation.

- [ ] **Step 4: Run adapter tests and existing export-contract tests**

Run: `uv run pytest tests/dashboard/test_export_data.py tests/unit/test_production_export_scripts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the adapter**

```bash
git add src/maple_monitor/dashboard/export_data.py tests/dashboard/test_export_data.py
git commit -m "feat: validate dashboard export archives"
```

---

### Task 2: Board-specific analysis projections

**Files:**
- Create: `src/maple_monitor/dashboard/export_analysis.py`
- Create: `tests/dashboard/test_export_analysis.py`

**Interfaces:**
- Consumes: `ExportBundle`
- Produces: `WindowSelection`, `select_window`, `rank_posts`, `job_comparison`, `collection_health`, and `semantic_availability`.

- [ ] **Step 1: Write failing tests for board windows, job fallback, metric ordering, normalization, and collection health**

```python
def test_job_window_falls_back_to_thirty_days_when_seven_days_is_sparse(bundle) -> None:
    result = select_window(bundle.posts, "hero", hours=168, fallback_hours=720, minimum=5)
    assert result.effective_hours == 720
    assert result.fallback_reason == "7일 표본 부족"


def test_rank_posts_never_calls_engagement_sentiment(bundle) -> None:
    result = rank_posts(bundle.posts, "free", "comments", hours=24)
    assert result.columns.tolist() == ["title", "comments", "published_at", "source_url"]
```

- [ ] **Step 2: Run the projection tests and verify RED**

Run: `uv run pytest tests/dashboard/test_export_analysis.py -q`

Expected: FAIL because projection functions do not exist.

- [ ] **Step 3: Implement deterministic projections**

```python
@dataclass(frozen=True)
class WindowSelection:
    rows: pd.DataFrame
    requested_hours: int
    effective_hours: int
    fallback_reason: str | None
    start: pd.Timestamp
    end: pd.Timestamp


def select_window(posts, analysis_unit, *, hours, fallback_hours=None, minimum=0):
    end = posts["published_at"].max()
    rows = _rows_since(posts, analysis_unit, end - pd.Timedelta(hours=hours))
    if fallback_hours and len(rows) < minimum:
        return _selection(posts, analysis_unit, end, fallback_hours, "7일 표본 부족")
    return WindowSelection(rows, hours, hours, None, rows["published_at"].min(), end)
```

Use raw totals plus per-post rates for job comparison. Treat `comments == 0` only as "댓글 0건", never as unresolved. Return semantic availability as false because the current contract has no semantic files.

- [ ] **Step 4: Run projection and source-registry tests**

Run: `uv run pytest tests/dashboard/test_export_analysis.py tests/unit/test_sources.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the projections**

```bash
git add src/maple_monitor/dashboard/export_analysis.py tests/dashboard/test_export_analysis.py
git commit -m "feat: derive board-specific dashboard views"
```

---

### Task 3: Dashboard shell and overview

**Files:**
- Create: `src/maple_monitor/dashboard/export_app.py`
- Create: `src/maple_monitor/dashboard/export_context.py`
- Create: `src/maple_monitor/dashboard/export_pages/__init__.py`
- Create: `src/maple_monitor/dashboard/export_pages/overview.py`
- Create: `src/maple_monitor/dashboard/export_pages/shared.py`
- Create: `tests/dashboard/test_export_overview.py`

**Interfaces:**
- Consumes: `MAPLE_EXPORT_PATH`, `load_export_archive`, and Task 2 projections.
- Produces: a top-navigation Streamlit entry point and shared factual-status components.

- [ ] **Step 1: Write failing AppTest coverage for missing path, valid overview, Korean copy, freshness, and semantic-unavailable state**

```python
def test_export_app_renders_factual_overview(monkeypatch, export_zip: Path) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(export_zip))
    page = AppTest.from_file(EXPORT_APP).run()
    assert not page.exception
    assert "종합 현황" in str(page)
    assert "감성 분석 데이터 없음" in str(page)
    assert "AI" not in str(page)
```

- [ ] **Step 2: Run the overview tests and verify RED**

Run: `uv run pytest tests/dashboard/test_export_overview.py -q`

Expected: FAIL because the export entry point does not exist.

- [ ] **Step 3: Implement cached context and top navigation**

```python
@st.cache_data(show_spinner="검증된 내보내기를 불러오는 중입니다")
def load_current_export(path_text: str) -> ExportBundle:
    return load_export_archive(Path(path_text))


pages = [
    st.Page("export_pages/overview.py", title="종합 현황", icon=":material/dashboard:"),
    st.Page("export_pages/jobs.py", title="직업 분석", icon=":material/groups:"),
    st.Page("export_pages/free.py", title="자유게시판", icon=":material/forum:"),
    st.Page("export_pages/qna.py", title="질문과 답변", icon=":material/help:"),
    st.Page("export_pages/tips.py", title="팁과 노하우", icon=":material/menu_book:"),
    st.Page("export_pages/operations.py", title="운영 상태", icon=":material/monitor_heart:"),
]
st.navigation(pages, position="top").run()
```

The overview shows factual freshness, post and unit coverage, collection success, leading free posts, and job engagement comparison. Use captions for metadata and a warning only for materially unavailable semantic analysis.

- [ ] **Step 4: Run overview tests and existing dashboard tests**

Run: `uv run pytest tests/dashboard/test_export_overview.py tests/dashboard/test_cumulative_page.py -q`

Expected: PASS; the database-backed app remains unchanged.

- [ ] **Step 5: Commit the shell and overview**

```bash
git add src/maple_monitor/dashboard/export_app.py src/maple_monitor/dashboard/export_context.py src/maple_monitor/dashboard/export_pages tests/dashboard/test_export_overview.py
git commit -m "feat: add export dashboard overview"
```

---

### Task 4: Board workspaces and operating status

**Files:**
- Create: `src/maple_monitor/dashboard/export_pages/jobs.py`
- Create: `src/maple_monitor/dashboard/export_pages/free.py`
- Create: `src/maple_monitor/dashboard/export_pages/qna.py`
- Create: `src/maple_monitor/dashboard/export_pages/tips.py`
- Create: `src/maple_monitor/dashboard/export_pages/operations.py`
- Create: `tests/dashboard/test_export_pages.py`

**Interfaces:**
- Consumes: the cached bundle and Task 2 projections.
- Produces: five direct page scripts with board-specific labels, windows, empty states, and evidence tables.

- [ ] **Step 1: Write failing page tests for each board's purpose and prohibited claims**

```python
@pytest.mark.parametrize(
    ("page_name", "required", "forbidden"),
    [
        ("jobs.py", "7일 표본", "긍정 반응"),
        ("free.py", "24시간 주요 게시물", "커뮤니티가 긍정"),
        ("qna.py", "댓글 0건", "미해결 확정"),
        ("tips.py", "30일 인기 정보", "논쟁도"),
        ("operations.py", "수집 실패", "정상 수집"),
    ],
)
def test_board_pages_use_source_appropriate_language(...):
    page = AppTest.from_file(EXPORT_PAGES / page_name).run()
    assert required in str(page)
    assert forbidden not in str(page)
```

- [ ] **Step 2: Run page tests and verify RED**

Run: `uv run pytest tests/dashboard/test_export_pages.py -q`

Expected: FAIL because the board page scripts do not exist.

- [ ] **Step 3: Implement the five pages**

Use `st.selectbox` for 48 jobs, `st.segmented_control` for the three engagement metrics, native bar charts for compact comparisons, and `st.dataframe` with number, datetime, and link column configuration for evidence. Each page displays its effective period, sample size, factual freshness, and semantic-unavailable state where applicable.

- [ ] **Step 4: Run all dashboard tests**

Run: `uv run pytest tests/dashboard -q`

Expected: PASS.

- [ ] **Step 5: Commit the board pages**

```bash
git add src/maple_monitor/dashboard/export_pages tests/dashboard/test_export_pages.py
git commit -m "feat: add board-specific dashboard workspaces"
```

---

### Task 5: Editorial theme, operations guide, and release verification

**Files:**
- Create: `.streamlit/config.toml`
- Modify: `docs/operations/vps-production.md`
- Create: `tests/dashboard/test_export_dashboard_e2e.py`

**Interfaces:**
- Consumes: the completed export dashboard.
- Produces: reproducible launch instructions and a verified light editorial presentation.

- [ ] **Step 1: Write failing tests for navigation, source evidence, and launch documentation**

```python
def test_operations_guide_documents_export_dashboard_launch() -> None:
    guide = Path("docs/operations/vps-production.md").read_text(encoding="utf-8")
    assert "MAPLE_EXPORT_PATH" in guide
    assert "maple_monitor/dashboard/export_app.py" in guide
```

- [ ] **Step 2: Run end-to-end tests and verify RED**

Run: `uv run pytest tests/dashboard/test_export_dashboard_e2e.py -q`

Expected: FAIL because the launch instructions and theme are absent.

- [ ] **Step 3: Add the native light theme and launch guide**

```toml
[theme]
base = "light"
primaryColor = "#315B75"
backgroundColor = "#F7F6F2"
secondaryBackgroundColor = "#ECEBE6"
textColor = "#18212B"
borderColor = "#D3D1C8"
baseRadius = "4px"
showWidgetBorder = true
chartCategoricalColors = ["#315B75", "#A64B45", "#73806B", "#8A7558", "#6B7280"]
```

Document PowerShell and shell launch commands using `MAPLE_EXPORT_PATH`. Do not document or commit the production archive itself.

- [ ] **Step 4: Run static, dashboard, and focused regression gates**

Run: `uv run ruff check src/maple_monitor/dashboard tests/dashboard`

Expected: PASS.

Run: `uv run pytest tests/dashboard tests/unit/test_sources.py tests/unit/test_production_export_scripts.py -q`

Expected: PASS.

- [ ] **Step 5: Run the app against the supplied production archive and inspect one screenshot**

Run: set `MAPLE_EXPORT_PATH` to `exports/production-20260716-190257.zip`, start `export_app.py` on a local 850x port, open the overview, and capture a screenshot.

Expected: all Korean labels render correctly; the first viewport communicates freshness, coverage, leading factual items, and semantic unavailability without decorative AI styling.

- [ ] **Step 6: Commit the release polish**

```bash
git add .streamlit/config.toml docs/operations/vps-production.md tests/dashboard/test_export_dashboard_e2e.py
git commit -m "docs: ship the export dashboard workflow"
```
