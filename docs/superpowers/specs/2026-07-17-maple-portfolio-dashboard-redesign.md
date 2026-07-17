# Maple community portfolio dashboard redesign

## Goal

Turn the export-backed MapleStory community dashboard into a recruiter-first portfolio that still
supports operational exploration. The first screen must explain the problem, evidence, engineering
quality, and AI experiment path before asking the viewer to interact.

## Audience and delivery

- Primary audience: reviewers of Nexon Korea's AI Engineer internship portfolio.
- Primary delivery: interactive Streamlit application, later hosted behind a shareable link.
- Secondary delivery: PPT/PDF narrative snapshots linked back to the hosted application through a
  URL or QR code.
- Future portability: analysis functions return serializable frames and dictionaries so the same
  figures can be rendered outside Streamlit without changing metric definitions.
- PPT and PDF are not treated as fully interactive surfaces; the hosted app is the canonical
  interactive artifact.

## Source and evidence boundaries

- Core source: checksum-verified production export ZIP selected by `MAPLE_EXPORT_PATH`.
- Current export contains post titles, board/job identity, publication timestamps, and cumulative
  views, recommendations, and comment counts.
- The export does not contain post bodies, comment text, topic labels, sentiment labels, or model
  outputs. The app must not infer or display those results as facts.
- Every displayed aggregation must reconcile to the selected effective evidence window.
- Job windows remain seven days with a visible 30-day fallback when the primary sample is sparse.

## Portfolio narrative

The default page follows this order:

1. Problem: structure class-specific requests and major community attention signals.
2. Evidence: show source size, freshness, checksums, and collection health.
3. Observation: show total posts, comments, views, and recommendations plus the job constellation.
4. Drill-down: send viewers to job and board-specific workspaces.
5. AI experiment design: show dataset design, labeling, baseline, SLM experiment, evaluation, and
   error-analysis plan as planned work rather than fabricated performance.
6. Limits and next steps: state the missing text/label fields and the collection expansion needed.

## Metric model

### Job comparison

For every collected job and its effective window, expose:

- post count;
- total comments, recommendations, and views;
- comments, recommendations, and views per post;
- effective window and fallback reason.

Totals describe volume. Per-post rates describe reaction density. The app does not combine the
three engagement counters into a hidden composite score.

### Selected job

The selected job displays four headline values together: posts, comments, views, and
recommendations. The sorting control includes the selected job's actual totals in its labels, for
example `댓글 1,240`, `추천 318`, and `조회 82,400`.

The evidence table always shows title, comments, recommendations, views, publication time, and the
source link. The selected counter controls ordering and visual emphasis only; it does not hide the
other counters.

### Job constellation

The distinctive portfolio chart is an Altair bubble scatter:

- x: post count;
- y: comments per post;
- bubble size: total views;
- bubble color: recommendations per post;
- tooltip: job, posts, all three totals, all three per-post rates, and effective period.

This chart reveals high-volume/high-discussion jobs without replacing the exact comparison table.
Color uses a single sequential indigo-to-gold scale so it remains interpretable as magnitude rather
than category.

## AI experiment design

The portfolio page maps directly to the linked Nexon AI Engineer role's stated work: dataset
design, labeling and quality review, hypothesis-driven experiments, model evaluation, analysis,
and documentation.

1. Sample across job, board, time, and engagement percentiles; include low-engagement controls so
   the dataset is not only popular posts.
2. Label intent (`complaint`, `request`, `debate`, `question`, `praise`, `information`) and a
   hierarchical issue topic (`balance`, `skill structure`, `usability`, `bug`, `boss`, `economy`,
   and reviewed additions).
3. Define a reviewed gold set and measure inter-annotator agreement before training.
4. Establish a TF-IDF linear baseline, then compare a Korean small language model fine-tune.
5. Use temporal holdout and held-out-job evaluation to test drift and cross-job generalization.
6. Report macro-F1, label-level F1, calibration, confusion patterns, and representative errors.
7. When bodies and comments become available, compare title-only and full-context models.

The page labels each step as `available`, `designed`, or `requires text labels`. It shows no model
score until a versioned experiment result exists.

## Visual system

### Visual thesis

The dashboard is a community observation record kept in Lethe's mansion: deep midnight indigo,
moon-silver typography, a restrained oath-gold accent, and luminous orbit lines surrounding one
official Lethe key visual.

### Official imagery

- Use only assets retrieved from official Nexon/MapleStory properties.
- The hero may use the official Lethe character/key art directly.
- Do not use fan art, blog mirrors, video thumbnails, or search-result copies.
- Store the original source URL and `© NEXON Korea` attribution in the app and asset manifest.
- Keep the image on the visual side of the hero; do not place dense data on top of the character.

### Palette and typography

- Main background: midnight indigo, not pure black.
- Secondary surfaces: layered blue-violet.
- Primary text: moon silver.
- Muted text: cool gray-blue.
- Primary accent: oath gold.
- Heading face: `Noto Serif KR`; body face: `Noto Sans KR`.
- Use theme configuration for global styling. Targeted CSS is allowed only for the explicitly
  requested hero treatment and subtle orbit decoration.

### Composition and interaction

- The first viewport is a poster-like hero, not a generic grid of cards.
- KPI metrics form one responsive row after the hero.
- Use one short hero entrance, a quiet orbit shimmer, and restrained hover emphasis.
- Respect reduced-motion settings and maintain WCAG AA contrast.
- Prefer native Streamlit controls, Altair, and dataframe column configuration.

## Export readiness

- Add a deterministic portfolio snapshot builder containing source metadata, global totals, job
  comparison rows, and the AI experiment-status model.
- Keep snapshot values JSON-serializable so later PPT/PDF generators can reuse them.
- The first implementation does not generate PPT or PDF; it establishes stable content and data
  contracts for that follow-up.

## Error and empty states

- Preserve checksum, schema, and empty-export failures.
- A missing official image must degrade to a branded text hero without blocking data exploration.
- A job with no posts shows zero totals and no evidence table crash.
- Sparse-window fallbacks remain visible beside every affected comparison.

## Verification

- Unit tests reconcile job totals and per-post rates.
- AppTests verify the four selected-job metrics, totals embedded in sort labels, all engagement
  columns in the table, portfolio narrative, model-status wording, and image fallback.
- The full unit/dashboard suite and Ruff must pass.
- Load the real export and reconcile headline totals.
- Run the app locally and visually inspect the default portfolio page and job drill-down on desktop.

## References

- Nexon AI Engineer internship: https://careers.nexon.com/recruit/10000
- Official Lethe promotion: https://maplestory.nexon.com/promotion/event/2026/20260618/event01
