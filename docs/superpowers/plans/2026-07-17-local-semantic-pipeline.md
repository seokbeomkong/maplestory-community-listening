# Local Semantic Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a replayable local enrichment and Korean sentiment pipeline whose completed output is displayed as a company-facing Streamlit portfolio.

**Architecture:** Keep the verified production ZIP immutable. A local worker selects high-engagement posts, fetches public article bodies and comments, scans and labels sanitized text, and atomically writes a digest-bound sidecar artifact. Streamlit joins only a matching sidecar and otherwise keeps semantic output off portfolio pages.

**Tech Stack:** Python 3.12, httpx, BeautifulSoup/lxml, pandas, Streamlit, Typer, YAML, pytest.

## Global Constraints

- Metadata collection remains every six hours at minute 20 KST.
- Detail HTTP requests use one worker and a 1.5–3.0 second delay.
- The verified ZIP and its four-CSV checksum contract are never modified.
- Engagement counters prioritize samples but never determine sentiment.
- Body sentiment and comment reaction remain separate.
- Every displayed period is derived from the actual `published_at` rows.
- Portfolio pages contain no assistant-facing, “not executed,” or missing-data copy.
- Model retraining is monthly or drift-triggered, never per ZIP.

---

### Task 1: Analysis artifact contract and period labels

**Files:**
- Create: `src/maple_monitor/local/__init__.py`
- Create: `src/maple_monitor/local/artifacts.py`
- Modify: `src/maple_monitor/dashboard/export_context.py`
- Modify: `src/maple_monitor/dashboard/export_analysis.py`
- Test: `tests/unit/test_local_artifacts.py`
- Test: `tests/dashboard/test_export_context.py`
- Test: `tests/dashboard/test_export_analysis.py`

**Interfaces:**
- Produces: `archive_sha256(path: Path) -> str`.
- Produces: `analysis_directory(export_path: Path, root: Path) -> Path`.
- Produces: `load_analysis_artifact(export_path: Path, root: Path) -> AnalysisArtifact | None`.
- Produces: `source_period(rows: pd.DataFrame) -> SourcePeriod` with formatted KST dates.

- [ ] **Step 1: Write failing digest, manifest-mismatch, and date-range tests**

```python
def test_load_analysis_artifact_rejects_wrong_source_digest(export_zip, tmp_path):
    write_fixture_artifact(tmp_path, source_digest="0" * 64)
    assert load_analysis_artifact(export_zip, tmp_path) is None

def test_source_period_uses_actual_filtered_rows():
    rows = pd.DataFrame({"published_at": pd.to_datetime([
        "2026-04-17T01:00:00+09:00", "2026-07-17T23:00:00+09:00"
    ], utc=True)})
    assert source_period(rows).label == "2026.04.17–2026.07.17 게시물"
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_local_artifacts.py tests/dashboard/test_export_analysis.py -q`
Expected: collection errors for missing `maple_monitor.local.artifacts` and `source_period`.

- [ ] **Step 3: Implement the immutable artifact loader and period value object**

```python
@dataclass(frozen=True)
class AnalysisArtifact:
    manifest: Mapping[str, object]
    posts: pd.DataFrame
    comments: pd.DataFrame

def load_analysis_artifact(export_path: Path, root: Path) -> AnalysisArtifact | None:
    target = analysis_directory(export_path, root)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    if manifest["source_sha256"] != archive_sha256(export_path):
        return None
    return AnalysisArtifact(manifest, pd.read_csv(target / "semantic_posts.csv"),
                            pd.read_csv(target / "semantic_comments.csv"))
```

- [ ] **Step 4: Run focused tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_local_artifacts.py tests/dashboard/test_export_context.py tests/dashboard/test_export_analysis.py -q`
Expected: PASS.

- [ ] **Step 5: Commit the artifact contract**

```powershell
git add src/maple_monitor/local tests/unit/test_local_artifacts.py src/maple_monitor/dashboard/export_context.py src/maple_monitor/dashboard/export_analysis.py tests/dashboard/test_export_context.py tests/dashboard/test_export_analysis.py
git commit -m "feat: add digest-bound semantic artifacts"
```

### Task 2: Bounded article and comment enrichment

**Files:**
- Create: `src/maple_monitor/local/detail_client.py`
- Create: `src/maple_monitor/local/detail_parser.py`
- Create: `tests/fixtures/detail_post.html`
- Create: `tests/fixtures/detail_comments.json`
- Test: `tests/unit/test_detail_client.py`
- Test: `tests/unit/test_detail_parser.py`

**Interfaces:**
- Produces: `select_detail_candidates(posts: pd.DataFrame, *, window_days: int, per_metric: int) -> pd.DataFrame`.
- Produces: `fetch_post_detail(client: httpx.Client, board_id: int, post_id: int) -> RawDetail`.
- Produces: `parse_article(html: bytes) -> ParsedArticle`.
- Produces: `parse_comments(payload: bytes) -> ParsedComments`.

- [ ] **Step 1: Write failing selection and parser tests**

```python
def test_select_candidates_takes_each_metrics_leader_per_unit():
    selected = select_detail_candidates(posts, window_days=90, per_metric=1)
    assert set(selected["selection_reason"]) == {"comments", "recommendations", "views"}
    assert not selected.duplicated(["board_id", "post_id"]).any()

def test_parse_comments_removes_profiles_and_preserves_threads():
    result = parse_comments(FIXTURE.read_bytes())
    assert result.reported_count == 2
    assert result.comments[1].parent_id == result.comments[0].comment_id
    assert result.comments[0].text == "밸런스 조정이 필요합니다"
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_detail_client.py tests/unit/test_detail_parser.py -q`
Expected: import failures for the new detail modules.

- [ ] **Step 3: Implement strict host validation, byte caps, parsing, and count completeness**

```python
def fetch_post_detail(client, board_id, post_id):
    article = client.get(f"https://www.inven.co.kr/board/maple/{board_id}/{post_id}")
    comments = client.post(COMMENT_URL, data={"comeidx": str(board_id),
        "articlecode": str(post_id), "sortorder": "date", "act": "list", "out": "json"})
    return RawDetail(article.content, comments.content)

def parse_article(html):
    soup = BeautifulSoup(html, "lxml")
    content = soup.select_one("#powerbbsContent")
    if content is None:
        raise DetailParseError("article body is missing")
    return ParsedArticle(normalize_text(content.get_text(" ", strip=True)))
```

- [ ] **Step 4: Run unit tests plus one read-only live smoke check**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_detail_client.py tests/unit/test_detail_parser.py -q`
Expected: PASS; live test is opt-in and confirms HTTP 200 plus a non-empty body.

- [ ] **Step 5: Commit detail enrichment**

```powershell
git add src/maple_monitor/local/detail_client.py src/maple_monitor/local/detail_parser.py tests/unit/test_detail_client.py tests/unit/test_detail_parser.py tests/fixtures/detail_post.html tests/fixtures/detail_comments.json
git commit -m "feat: collect selected post bodies and comments"
```

### Task 3: Versioned Korean opinion baseline and atomic refresh command

**Files:**
- Create: `config/analysis_rules.yaml`
- Create: `src/maple_monitor/local/opinion.py`
- Create: `src/maple_monitor/local/pipeline.py`
- Modify: `src/maple_monitor/cli.py`
- Test: `tests/unit/test_opinion_baseline.py`
- Test: `tests/unit/test_local_pipeline.py`
- Test: `tests/unit/test_cli.py`

**Interfaces:**
- Produces: `classify_text(text: str, rules: AnalysisRules) -> TextLabel`.
- Produces: `analyze_post(body: str, comments: Sequence[str], rules: AnalysisRules) -> PostLabel`.
- Produces: `refresh_analysis(export_path: Path, analysis_root: Path, settings_path: Path, *, force: bool = False) -> RefreshSummary`.
- Produces CLI: `maple-monitor analyze-export --export-path PATH --analysis-root PATH`.

- [ ] **Step 1: Write failing separate body/comment and replay tests**

```python
def test_body_and_comment_reaction_are_separate(rules):
    label = analyze_post("스킬 개선이 필요합니다", ["좋다", "기대된다"], rules)
    assert label.intent == "request"
    assert label.body_sentiment == "negative"
    assert label.comment_reaction == "positive"

def test_refresh_skips_matching_complete_artifact(export_zip, tmp_path, fake_fetcher):
    first = refresh_analysis(export_zip, tmp_path, SETTINGS, fetcher=fake_fetcher)
    second = refresh_analysis(export_zip, tmp_path, SETTINGS, fetcher=fake_fetcher)
    assert first.fetched_posts > 0
    assert second.fetched_posts == 0
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_opinion_baseline.py tests/unit/test_local_pipeline.py tests/unit/test_cli.py -q`
Expected: missing opinion and pipeline modules.

- [ ] **Step 3: Implement versioned rules, scanner exclusion, evidence, and atomic directory replace**

```python
@dataclass(frozen=True)
class TextLabel:
    sentiment: Literal["positive", "neutral", "negative", "mixed"]
    topic: str
    intent: str
    confidence: float
    evidence_terms: tuple[str, ...]

def classify_text(text, rules):
    normalized = normalize_text(text)
    positive = matched_terms(normalized, rules.positive)
    negative = matched_terms(normalized, rules.negative)
    sentiment = resolve_sentiment(positive, negative)
    return TextLabel(sentiment, best_topic(normalized, rules),
                     best_intent(normalized, rules), confidence(positive, negative),
                     tuple((positive + negative)[:5]))
```

- [ ] **Step 4: Run unit and CLI tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_opinion_baseline.py tests/unit/test_local_pipeline.py tests/unit/test_cli.py -q`
Expected: PASS with no network access in tests.

- [ ] **Step 5: Commit the executable baseline**

```powershell
git add config/analysis_rules.yaml src/maple_monitor/local/opinion.py src/maple_monitor/local/pipeline.py src/maple_monitor/cli.py tests/unit/test_opinion_baseline.py tests/unit/test_local_pipeline.py tests/unit/test_cli.py
git commit -m "feat: add reproducible Korean opinion baseline"
```

### Task 4: Company-facing portfolio and semantic board views

**Files:**
- Create: `src/maple_monitor/dashboard/export_semantics.py`
- Modify: `src/maple_monitor/dashboard/export_context.py`
- Modify: `src/maple_monitor/dashboard/export_pages/overview.py`
- Modify: `src/maple_monitor/dashboard/export_pages/jobs.py`
- Modify: `src/maple_monitor/dashboard/export_pages/free.py`
- Modify: `src/maple_monitor/dashboard/export_pages/qna.py`
- Modify: `src/maple_monitor/dashboard/export_pages/tips.py`
- Replace: `src/maple_monitor/dashboard/export_pages/experiment.py`
- Modify: `src/maple_monitor/dashboard/export_theme.py`
- Test: `tests/dashboard/test_export_pages.py`
- Test: `tests/dashboard/test_export_experiment.py`
- Test: `tests/dashboard/test_export_overview.py`
- Test: `tests/dashboard/test_export_dashboard_e2e.py`

**Interfaces:**
- Consumes: `AnalysisArtifact` and `SourcePeriod` from Task 1.
- Produces: `semantic_summary(artifact, analysis_unit) -> SemanticSummary`.
- Produces: `render_semantic_summary(summary) -> None`.

- [ ] **Step 1: Write failing copy, period, workflow, and semantic-result tests**

```python
def test_portfolio_contains_completed_workflow_and_no_meta_copy(app_with_analysis):
    text = rendered_text(app_with_analysis)
    assert "실시간 유저 반응 관측" in text
    assert "2026.04.17–2026.07.17 게시물" in text
    assert "본문·댓글 수집" in text
    assert "MODEL DEVELOPMENT BLUEPRINT" not in text
    assert "데이터 없음" not in text
    assert "채용 직무와 연결" not in text

def test_job_page_shows_actual_body_and_comment_labels(app_with_analysis):
    text = rendered_text(app_with_analysis)
    assert "불만 40%" in text
    assert "댓글 반응" in text
    assert "domain-lexicon-v1" in text
```

- [ ] **Step 2: Run dashboard tests and confirm failure**

Run: `.venv\Scripts\python.exe -m pytest tests/dashboard -q`
Expected: failures for old meta copy and missing semantic fixture output.

- [ ] **Step 3: Implement the project flow, source-period captions, semantic summaries, and model story**

```python
st.header("실시간 유저 반응 관측")
render_pipeline_flow([
    "6시간 메타데이터 수집", "상위 게시물 선별", "본문·댓글 수집",
    "감성·의도·주제 추론", "30초 내 대시보드 반영",
])
summary = semantic_summary(artifact, selected_unit)
render_distribution("작성 글의 의도", summary.intent_distribution)
render_distribution("댓글 반응", summary.comment_sentiment_distribution)
st.caption(f"{summary.period.label} · 게시물 {summary.posts}건 · 댓글 {summary.comments}건 · {summary.model_version}")
```

- [ ] **Step 4: Run all dashboard tests**

Run: `.venv\Scripts\python.exe -m pytest tests/dashboard -q`
Expected: PASS; all banned phrases absent.

- [ ] **Step 5: Commit portfolio integration**

```powershell
git add src/maple_monitor/dashboard tests/dashboard
git commit -m "feat: present source-backed community sentiment"
```

### Task 5: Automatic local refresh and verified handoff

**Files:**
- Modify: `scripts/start-local-dashboard.ps1`
- Modify: `docs/portfolio/local-data-refresh.md`
- Modify: `docs/operations/vps-production.md`
- Test: `tests/dashboard/test_export_dashboard_e2e.py`
- Test: `tests/unit/test_production_export_scripts.py`

**Interfaces:**
- Consumes CLI `analyze-export` from Task 3.
- Produces a one-command refresh-and-run PowerShell entry point.

- [ ] **Step 1: Write failing launcher tests**

```python
def test_launcher_runs_analysis_before_streamlit():
    script = SCRIPT.read_text(encoding="utf-8")
    assert "analyze-export" in script
    assert script.index("analyze-export") < script.index("streamlit run")
    assert "MAPLE_ANALYSIS_ROOT" in script
```

- [ ] **Step 2: Run launcher tests and confirm failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_production_export_scripts.py tests/dashboard/test_export_dashboard_e2e.py -q`
Expected: launcher does not yet invoke analysis.

- [ ] **Step 3: Invoke incremental analysis before Streamlit and document cadence**

```powershell
$analysisRoot = Join-Path $resolvedExportRoot "analysis"
& $pythonPath -m maple_monitor.cli analyze-export --export-path $resolvedExportRoot --analysis-root $analysisRoot
if ($LASTEXITCODE -ne 0) { throw "Local semantic analysis failed." }
$env:MAPLE_ANALYSIS_ROOT = $analysisRoot
& $pythonPath -m streamlit run $appPath --server.port $Port
```

- [ ] **Step 4: Run the actual archive, full suite, lint, and visual check**

Run: `.venv\Scripts\python.exe -m maple_monitor.cli analyze-export --export-path C:\Users\tjrqj\Documents\Maplestory\exports\production-20260716-190257.zip --analysis-root C:\Users\tjrqj\Documents\Maplestory\exports\analysis`
Expected: a complete digest-matched artifact with non-zero post and comment labels.

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: PASS.

Run: `.venv\Scripts\ruff.exe check .`
Expected: PASS.

Start the dashboard, capture one browser screenshot, and confirm character focus, Korean glyphs,
workflow readability, source period, sentiment charts, and model version.

- [ ] **Step 5: Commit operations and documentation**

```powershell
git add scripts/start-local-dashboard.ps1 docs/portfolio/local-data-refresh.md docs/operations/vps-production.md tests
git commit -m "feat: refresh local analysis with each export"
```
