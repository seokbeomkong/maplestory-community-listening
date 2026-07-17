# Maple portfolio dashboard redesign implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a recruiter-first, Lethe-themed Streamlit portfolio with complete job engagement metrics, an interpretable constellation chart, and a truthful AI experiment-design narrative.

**Architecture:** Extend the existing typed export analysis layer with reusable job aggregates and a JSON-serializable portfolio snapshot. Keep Streamlit page scripts thin by moving chart and presentation transforms into focused modules. Use the existing multi-page entrypoint, replace the default overview with the portfolio narrative, add one AI experiment page, and preserve every existing board workspace.

**Tech Stack:** Python 3.12, pandas, Altair, Streamlit 1.57, pytest, Streamlit AppTest, Ruff

## Global Constraints

- The checksum-verified production ZIP selected by `MAPLE_EXPORT_PATH` remains the only source of displayed facts.
- Never display topic, sentiment, or model performance as observed data while bodies, comments, labels, and experiment outputs are absent.
- Job evidence uses seven days with a visibly disclosed 30-day sparse-sample fallback.
- Views, recommendations, and comments remain separate metrics; no hidden composite score.
- Only official Nexon/MapleStory Lethe imagery may be bundled, with source URL and `© NEXON Korea` attribution.
- The hosted Streamlit app is the canonical interactive artifact; PPT/PDF reuse the snapshot contract later.

---

### Task 1: Complete the reusable job metric and portfolio snapshot model

**Files:**
- Modify: `src/maple_monitor/dashboard/export_analysis.py`
- Create: `src/maple_monitor/dashboard/export_presentation.py`
- Modify: `tests/dashboard/test_export_analysis.py`
- Create: `tests/dashboard/test_export_presentation.py`

**Interfaces:**
- Produces: `job_comparison(posts, hours=168, fallback_hours=720, minimum=5) -> pd.DataFrame` with `total_views` and `views_per_post` in addition to existing fields.
- Produces: `engagement_totals(rows: pd.DataFrame) -> dict[str, int]` with `posts`, `comments`, `recommendations`, and `views`.
- Produces: `portfolio_snapshot(bundle: ExportBundle) -> dict[str, object]`, containing ISO timestamp strings, integer totals, checksum state, collection health, and job records.

- [ ] **Step 1: Write failing aggregate and serialization tests**

```python
def test_job_comparison_includes_view_totals_and_density() -> None:
    hero = job_comparison(_posts(), minimum=1).query("analysis_unit == 'hero'").iloc[0]
    assert hero["total_views"] == 300
    assert hero["views_per_post"] == 150.0

def test_portfolio_snapshot_is_json_serializable() -> None:
    snapshot = portfolio_snapshot(_bundle())
    assert snapshot["totals"]["posts"] == len(_bundle().posts)
    json.dumps(snapshot, ensure_ascii=False)
```

- [ ] **Step 2: Run the tests and verify the missing fields/functions fail**

Run: `uv run pytest tests/dashboard/test_export_analysis.py tests/dashboard/test_export_presentation.py -q`

Expected: failures for missing `total_views`, `views_per_post`, and `portfolio_snapshot`.

- [ ] **Step 3: Implement exact totals, densities, and the serializable snapshot**

```python
def engagement_totals(rows: pd.DataFrame) -> dict[str, int]:
    return {
        "posts": len(rows),
        "comments": int(rows["comments"].sum()),
        "recommendations": int(rows["recommendations"].sum()),
        "views": int(rows["views"].sum()),
    }
```

Build job records from `job_comparison`, convert missing fallback reasons to `None`, and convert
timestamps with `.isoformat()` before returning the snapshot.

- [ ] **Step 4: Run the focused tests and commit**

Run: `uv run pytest tests/dashboard/test_export_analysis.py tests/dashboard/test_export_presentation.py -q`

Expected: all focused tests pass.

Commit: `git commit -am "feat: expose portfolio-ready engagement metrics"`

### Task 2: Make the job workspace self-explanatory

**Files:**
- Modify: `src/maple_monitor/dashboard/export_analysis.py`
- Modify: `src/maple_monitor/dashboard/export_pages/jobs.py`
- Modify: `src/maple_monitor/dashboard/export_pages/shared.py`
- Modify: `tests/dashboard/test_export_analysis.py`
- Modify: `tests/dashboard/test_export_pages.py`

**Interfaces:**
- Changes: `rank_posts(rows, metric, limit=10)` always returns `title`, `comments`, `recommendations`, `views`, `published_at`, and `source_url`, ordered by `metric`.
- Consumes: `engagement_totals(selection.rows)` from Task 1.

- [ ] **Step 1: Write failing tests for complete evidence and labeled controls**

```python
def test_rank_posts_keeps_all_engagement_counters() -> None:
    ranked = rank_posts(_posts(), "comments", limit=3)
    assert ranked.columns.tolist() == [
        "title", "comments", "recommendations", "views", "published_at", "source_url"
    ]

def test_job_page_shows_four_totals_and_metric_counts(monkeypatch, export_zip) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(export_zip))
    page = AppTest.from_file(_PAGES / "jobs.py").run(timeout=10)
    assert {metric.label for metric in page.metric} >= {"게시물", "댓글", "추천", "조회"}
    assert "댓글 8" in str(page)
    assert "추천 3" in str(page)
    assert "조회 500" in str(page)
```

- [ ] **Step 2: Run the focused tests and verify the expected failures**

Run: `uv run pytest tests/dashboard/test_export_analysis.py tests/dashboard/test_export_pages.py -q`

Expected: the evidence column assertion and fourth metric/control-label assertions fail.

- [ ] **Step 3: Implement four KPIs, counted sort options, and the complete table**

Use option strings generated from selected-job totals:

```python
metric_options = {
    f"댓글 {totals['comments']:,}": "comments",
    f"추천 {totals['recommendations']:,}": "recommendations",
    f"조회 {totals['views']:,}": "views",
}
```

Configure all three numeric columns in `render_evidence_table`; use the selected metric only for
ordering and label the section with the active metric.

- [ ] **Step 4: Run the focused tests and commit**

Run: `uv run pytest tests/dashboard/test_export_analysis.py tests/dashboard/test_export_pages.py -q`

Expected: all focused tests pass.

Commit: `git commit -am "feat: clarify job engagement drill-down"`

### Task 3: Add the recruiter-first portfolio narrative and constellation chart

**Files:**
- Create: `src/maple_monitor/dashboard/export_charts.py`
- Replace content: `src/maple_monitor/dashboard/export_pages/overview.py`
- Modify: `src/maple_monitor/dashboard/export_app.py`
- Create: `tests/dashboard/test_export_charts.py`
- Modify: `tests/dashboard/test_export_overview.py`
- Modify: `tests/dashboard/test_export_dashboard_e2e.py`

**Interfaces:**
- Produces: `job_constellation(comparison: pd.DataFrame) -> alt.Chart`.
- Consumes: `portfolio_snapshot(bundle)` and `job_comparison(bundle.posts)`.

- [ ] **Step 1: Write failing chart and default-page narrative tests**

```python
def test_constellation_encodes_interpretable_job_metrics() -> None:
    spec = job_constellation(job_comparison(_posts(), minimum=1)).to_dict()
    encoding = spec["encoding"]
    assert encoding["x"]["field"] == "sample_size"
    assert encoding["y"]["field"] == "comments_per_post"
    assert encoding["size"]["field"] == "total_views"
    assert encoding["color"]["field"] == "recommendations_per_post"

def test_overview_tells_the_portfolio_story(monkeypatch, export_zip) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(export_zip))
    page = AppTest.from_file(_PAGES / "overview.py").run(timeout=10)
    text = str(page)
    assert "커뮤니티의 목소리를 검증 가능한 데이터로" in text
    assert "직업 별자리" in text
    assert "데이터 한계" in text
```

- [ ] **Step 2: Run the tests and verify missing chart/story failures**

Run: `uv run pytest tests/dashboard/test_export_charts.py tests/dashboard/test_export_overview.py tests/dashboard/test_export_dashboard_e2e.py -q`

Expected: import or content failures for the new chart and narrative.

- [ ] **Step 3: Implement the Altair chart and summary-first portfolio page**

Use `mark_circle(opacity=0.82, stroke="#E8D89A")`, quantitative axes with zero disabled only when
the domain requires it, a sequential indigo-to-gold scale, and a tooltip containing exact totals,
rates, and effective period. Keep the exact job table below the chart.

The default page renders: hero, source receipt, four global engagement totals, constellation,
engineering evidence, AI experiment preview, and limitations.

- [ ] **Step 4: Rename the default navigation item and run tests**

Change `종합 현황` to `프로젝트` with `:material/auto_awesome_mosaic:` while preserving the page
as the default route.

Run: `uv run pytest tests/dashboard/test_export_charts.py tests/dashboard/test_export_overview.py tests/dashboard/test_export_dashboard_e2e.py -q`

Expected: all focused tests pass.

- [ ] **Step 5: Commit**

Commit: `git commit -am "feat: tell the community analysis portfolio story"`

### Task 4: Add the truthful AI experiment-design page

**Files:**
- Create: `src/maple_monitor/dashboard/export_pages/experiment.py`
- Modify: `src/maple_monitor/dashboard/export_app.py`
- Modify: `tests/dashboard/test_export_pages.py`

**Interfaces:**
- Produces: a direct Streamlit page with no model inference or persisted state.
- Consumes: source coverage from `require_export_bundle()` and status definitions local to the page.

- [ ] **Step 1: Write a failing AppTest for the role-aligned experiment path**

```python
def test_experiment_page_separates_evidence_from_planned_model_work(monkeypatch, export_zip) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(export_zip))
    page = AppTest.from_file(_PAGES / "experiment.py").run(timeout=10)
    text = str(page)
    assert "데이터셋 설계" in text
    assert "TF-IDF 기준선" in text
    assert "한국어 소형 언어 모델" in text
    assert "Macro-F1" in text
    assert "실험 결과 없음" in text
```

- [ ] **Step 2: Run the test and verify the missing-page failure**

Run: `uv run pytest tests/dashboard/test_export_pages.py::test_experiment_page_separates_evidence_from_planned_model_work -q`

Expected: failure because `experiment.py` does not exist.

- [ ] **Step 3: Implement the page and navigation**

Render five concise stages with status badges: source available, label design designed, gold-set
review requires labeling, baseline designed, SLM/evaluation requires text labels. Include temporal
and held-out-job splits, macro-F1, calibration, agreement, and error-analysis outputs. Link to the
Nexon role and repeat that no model score exists.

- [ ] **Step 4: Run the page tests and commit**

Run: `uv run pytest tests/dashboard/test_export_pages.py -q`

Expected: all page tests pass.

Commit: `git commit -am "feat: document the AI experiment pathway"`

### Task 5: Apply the official Lethe visual system and asset attribution

**Files:**
- Create: `src/maple_monitor/dashboard/assets/lethe-key-art.webp`
- Create: `src/maple_monitor/dashboard/assets/README.md`
- Create: `src/maple_monitor/dashboard/export_style.py`
- Modify: `.streamlit/config.toml`
- Modify: `src/maple_monitor/dashboard/export_app.py`
- Modify: `src/maple_monitor/dashboard/export_pages/overview.py`
- Modify: `tests/dashboard/test_export_overview.py`

**Interfaces:**
- Produces: `apply_portfolio_style() -> None`, called once by the app before navigation.
- Produces: `hero_asset_path() -> Path | None`, returning `None` when the official asset is absent.

- [ ] **Step 1: Acquire and record one official asset**

Use the official promotion page's observed asset URL, store the source URL, retrieval date, title,
and `© NEXON Korea` in `assets/README.md`, and verify the downloaded image visually before use.

- [ ] **Step 2: Write failing asset fallback and attribution tests**

```python
def test_overview_has_official_asset_attribution(monkeypatch, export_zip) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(export_zip))
    page = AppTest.from_file(_PAGES / "overview.py").run(timeout=10)
    assert "© NEXON Korea" in str(page)
    assert "공식 레테 프로모션" in str(page)
```

Add a pure unit test that temporarily supplies a missing path and expects the hero renderer to
return the text-only state rather than raising.

- [ ] **Step 3: Run the tests and verify the expected failures**

Run: `uv run pytest tests/dashboard/test_export_overview.py -q`

Expected: attribution and fallback behavior are missing.

- [ ] **Step 4: Implement the theme and targeted hero styling**

Configure a dark midnight-indigo theme with moon-silver text, layered indigo surfaces, oath-gold
primary controls, Noto Serif KR headings, and Noto Sans KR body text. Target only keyed hero/orbit
containers with CSS; include a `prefers-reduced-motion` override. Keep the official character art
in the visual column and data in a separate column.

- [ ] **Step 5: Run focused tests and commit**

Run: `uv run pytest tests/dashboard/test_export_overview.py tests/dashboard/test_export_dashboard_e2e.py -q`

Expected: all focused tests pass.

Commit: `git commit -am "feat: apply the official Lethe portfolio theme"`

### Task 6: Verify real data, visual quality, and handoff readiness

**Files:**
- Modify: `docs/operations/vps-production.md`
- Modify: `tests/dashboard/test_export_pages.py` only if visual smoke exposes a behavioral regression

**Interfaces:**
- Consumes all previous tasks; produces no new runtime API.

- [ ] **Step 1: Run the full automated verification**

Run: `uv run pytest tests/unit tests/dashboard -q`

Expected: zero failures.

Run: `uv run ruff check src/maple_monitor/dashboard tests/dashboard`

Expected: `All checks passed!`

- [ ] **Step 2: Reconcile the real export**

Load `exports/production-20260716-190257.zip`, assert the existing 2,179 post, 51 Analysis Unit,
3,948 ranking, 26 run, and four checksum counts, then print global engagement totals and compare
them with the default page.

- [ ] **Step 3: Run and visually verify the app**

Start on a free 8500-series port with the real `MAPLE_EXPORT_PATH`. Inspect the default page and
job page at desktop width. Confirm the official image is sharp, text contrast is readable, the
constellation and evidence table render, and controls do not overflow.

- [ ] **Step 4: Document the reproducible run command and export contract**

Add the exact PowerShell environment variable and `uv run streamlit run` command, and note that
future PPT/PDF generators must consume `portfolio_snapshot()` rather than recalculate metrics.

- [ ] **Step 5: Commit**

Commit: `git commit -am "docs: hand off the portfolio dashboard"`
