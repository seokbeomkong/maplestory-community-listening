# Semantic Sample and Readability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand evidence-backed semantic samples, prove job-level isolation, and replace unreadable charts with four exact distribution panels plus classification guidance.

**Architecture:** A versioned selection policy chooses different per-metric limits for job and general units. The refresh pipeline reuses matching rows from the prior digest-bound artifact and fetches only missing candidates. Pure distribution helpers feed a Streamlit presentation layer that shows exact counts, shares, scope, and the rule-model methodology.

**Tech Stack:** Python 3.12, pandas, Streamlit, pytest, YAML, existing Inven detail client.

## Global Constraints

- Candidate window is exactly 90 days.
- Job units select top 5 per comments, recommendations, and views; `free`, `qna`, and `tips` select top 20 per metric.
- Job pages may render only rows whose `analysis_unit` equals the selected job.
- Engagement metadata selects evidence and never determines sentiment.
- Existing complete rows for the same ZIP digest and model version are reused during policy expansion.

---

### Task 1: Versioned Candidate Policy and Incremental Expansion

**Files:**
- Modify: `config/analysis_rules.yaml`
- Modify: `src/maple_monitor/local/detail_parser.py`
- Modify: `src/maple_monitor/local/pipeline.py`
- Test: `tests/unit/test_detail_parser.py`
- Test: `tests/dashboard/test_export_context.py`

**Interfaces:**
- Produces: `candidate_limits() -> dict[str, int]`
- Produces: `select_detail_candidates(..., per_metric_by_unit: Mapping[str, int] | None) -> pd.DataFrame`
- Produces: manifest field `selection_policy` with policy version and exact limits.

- [ ] **Step 1: Write failing candidate-limit tests**

```python
selected = select_detail_candidates(
    rows,
    window_days=90,
    per_metric_by_unit={"hero": 2, "free": 3},
)
assert selected.groupby("analysis_unit").size().to_dict() == {"free": 9, "hero": 6}
assert set(selected.loc[selected.analysis_unit == "hero", "board_id"]) == {2294}
```

- [ ] **Step 2: Run the tests and confirm the current fixed limit fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_detail_parser.py -q`

- [ ] **Step 3: Implement variable limits and policy manifest**

```python
SELECTION_POLICY = {
    "version": "engagement-top-v2",
    "window_days": 90,
    "job_per_metric": 5,
    "general_per_metric": 20,
}
```

Move the reuse return until after candidate calculation. Return immediately only when the stored
policy equals `SELECTION_POLICY`; otherwise retain selected existing keys and fetch the missing set.

- [ ] **Step 4: Add and pass an incremental-reuse test**

Create an old-policy artifact with one candidate row removed, rerun `refresh_analysis`, and assert the
fetcher is called only for the missing key while the final artifact contains every candidate.

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_detail_parser.py tests/dashboard/test_export_context.py -q`

### Task 2: Title-Aware Topic and Intent Classification

**Files:**
- Modify: `src/maple_monitor/local/opinion.py`
- Modify: `src/maple_monitor/local/pipeline.py`
- Test: `tests/unit/test_opinion_baseline.py`

**Interfaces:**
- Changes: `analyze_post(body, comments, rules, *, title="") -> PostLabel`
- Preserves: body sentiment from body only and comment reaction from comments only.

- [ ] **Step 1: Write a failing title-context test**

```python
label = analyze_post("개선이 필요합니다", (), rules, title="보스 극딜 구조 토론")
assert label.topic == "보스·전투"
assert label.intent == "debate"
```

- [ ] **Step 2: Verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_opinion_baseline.py -q`

- [ ] **Step 3: Classify topic and intent from title plus body**

Keep `body_sentiment` from `classify_text(body)`. Obtain topic and intent from
`classify_text(f"{title} {body}")`, then pass `title=str(row.title)` from the pipeline.

- [ ] **Step 4: Verify GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_opinion_baseline.py -q`

### Task 3: Exact Four-Panel Semantic Presentation

**Files:**
- Modify: `src/maple_monitor/dashboard/export_semantics.py`
- Modify: `src/maple_monitor/dashboard/export_theme.py`
- Modify: `src/maple_monitor/dashboard/export_pages/jobs.py`
- Modify: `src/maple_monitor/dashboard/export_pages/free.py`
- Modify: `src/maple_monitor/dashboard/export_pages/qna.py`
- Modify: `src/maple_monitor/dashboard/export_pages/tips.py`
- Test: `tests/dashboard/test_export_semantics.py`
- Test: `tests/dashboard/test_export_pages.py`

**Interfaces:**
- Produces: `distribution_rows(values, labels=None) -> tuple[DistributionRow, ...]`
- Changes: `render_semantic_summary(..., scope_label: str) -> None`

- [ ] **Step 1: Write failing distribution and job-scope tests**

```python
rows = distribution_rows(pd.Series(["negative", "negative", "positive"]), _SENTIMENT)
assert [(row.label, row.count, row.share) for row in rows] == [
    ("부정", 2, 2 / 3), ("긍정", 1, 1 / 3)
]
assert "괴도팬텀 직업 카테고리 게시물만" in str(job_page)
```

- [ ] **Step 2: Verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/dashboard/test_export_semantics.py tests/dashboard/test_export_pages.py -q`

- [ ] **Step 3: Implement four axis-free panels**

Render `topic`, `intent`, `body_sentiment`, and `comment_reaction` in a 2×2 grid. Each row shows
label, count, share, and a CSS width bar. Add selected-job scope and the exact 90-day selection policy.

- [ ] **Step 4: Implement the methodology expander**

The `분류 기준과 해석 방법` expander must state the source text, keyword-hit rule, tie/default
behavior, comment aggregation, and the separation of engagement metadata from sentiment.

- [ ] **Step 5: Verify GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/dashboard/test_export_semantics.py tests/dashboard/test_export_pages.py -q`

### Task 4: Real Artifact Expansion and Final Verification

**Files:**
- Update derived artifact outside git: `exports/analysis/production-20260716-190257/*`
- Modify documentation only if observed behavior differs: `docs/portfolio/local-data-refresh.md`

**Interfaces:**
- Consumes: versioned selection policy and incremental refresh.
- Produces: a digest-matched semantic artifact with expanded candidate coverage.

- [ ] **Step 1: Run the real incremental refresh**

```powershell
.venv\Scripts\python.exe -m maple_monitor.cli analyze-export `
  --export-path "C:\Users\tjrqj\Documents\Maplestory\exports\production-20260716-190257.zip" `
  --analysis-root "C:\Users\tjrqj\Documents\Maplestory\exports\analysis"
```

- [ ] **Step 2: Verify scope and counts**

Assert every semantic row has the same `analysis_unit` and `board_id` mapping as its source export;
report total candidates and the min/median/max analyzed rows per job.

- [ ] **Step 3: Run the non-integration suite and linter**

Run: `.venv\Scripts\python.exe -m pytest -q --ignore=tests/integration`

Run: `.venv\Scripts\ruff.exe check .`

- [ ] **Step 4: Inspect overview, jobs, free, qna, and tips in the browser**

Confirm Korean text has no overlap, all four panels show exact counts and shares, selected job scope is
visible, the methodology expander is readable, and the browser console has no errors.
