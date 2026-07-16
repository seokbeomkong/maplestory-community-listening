# Maple Community Dashboard Design

## Goal and Audience

Create a private decision-support dashboard for MapleStory operations and planning teams. It must offer a concise operating overview and evidence-backed board-specific analysis without making unsupported semantic claims.

The product requirements are defined in `docs/brainstorms/2026-07-17-maple-community-dashboard-requirements.md`.

## Current Data Baseline

The production archive contains four CSV files plus checksums:

- 2,179 latest post-metric rows across 51 analysis units
- 3,948 cumulative ranking rows at one as-of slot
- 26 collection runs, including 25 successes and one failed warrior run
- no quarantine rows

Checksums match, required fields are populated, and expected post and ranking keys have no duplicates. The current export has no body text, comment text, semantic labels, or historical snapshot series. Only 24 of 153 unit-metric ranking groups contain 50 eligible rows, so every view must disclose sample size rather than imply full coverage.

## Information Architecture

1. **종합 현황** — leading issues, job complaint and request signals, free-board reaction, and data status
2. **직업 분석** — 48-job comparison followed by job detail
3. **자유게시판** — 24-hour issue pulse, reaction, controversy, and diffusion
4. **질문과 답변** — 7-day repeated questions, knowledge gaps, and unresolved themes
5. **팁과 노하우** — 30-day useful themes, engagement, freshness, and sustained interest
6. **운영 상태** — collection failures, sample coverage, analysis completeness, freshness, and confidence

## Board-Specific Analytical Model

| Workspace | Primary question | Default window | Main outputs |
|---|---|---:|---|
| Jobs | What are players complaining about, requesting, or debating? | 7 days | topic mix, intent, author sentiment, comment reaction, representative posts |
| Free | What is the largest current issue and how is the community reacting? | 24 hours | issue share, movement, sentiment, controversy, diffusion |
| Q&A | Where are players confused or missing information? | 7 days | repeated questions, low-response themes, unresolved needs |
| Tips | What information is useful or sustaining attention? | 30 days | topic mix, engagement, freshness, sustained interest |

Low-volume job views may expand from 7 to 30 days. The effective window and reason must remain visible.

## Dashboard Components

### Overview

Use a short issue ledger rather than a wall of KPI cards. Pair it with a job-topic heatmap, a free-board issue ranking, and a compact data-health strip. Every item links to its detail and evidence.

### Job Comparison and Detail

Compare jobs using normalized complaint and request rates alongside raw sample size. Use ranked topic bars and a dot comparison for author sentiment versus comment reaction. Finish with a compact evidence table containing title, engagement, period, confidence, and source link.

### Free, Q&A, and Tips

Free uses ranked issue bars, a reaction distribution, controversy markers, and trend lines when history exists. Q&A replaces sentiment emphasis with repeated and unresolved-question views. Tips emphasizes topic utility, engagement, and freshness rather than controversy.

### Operating Status

Show collection result, latest factual slot, semantic freshness, rows or units below sample thresholds, analysis completion, and configuration version. A failed or partial source remains attributable to its board and period.

## Data Flow and Degraded States

The first release validates the archive and derives board, job, ranking, engagement, and health views. Semantic components render an unavailable state rather than estimating sentiment from titles.

When body and comment exports arrive, analysis produces separate author and comment labels for topic, intent, sentiment, reaction, and confidence. Aggregates feed the existing workspaces without changing navigation.

When engagement is current but semantic analysis is stale, the dashboard displays current engagement and labels the semantic result with its own older freshness time. When history is absent, movement and rising panels remain disabled.

## Visual Direction

Use a restrained editorial and research style: light neutral background, dark navy text, muted red and blue for opposing reactions, and gray for neutral or unavailable states. Avoid gradients, neon colors, decorative AI imagery, chat bubbles, excessive rounding, and generic narrative cards.

Prefer ranked bars, heatmaps, dot comparisons, sparklines, and tables. Labels should be short Korean phrases. Color must always be accompanied by text or numeric values.

## Validation

- Verify archive checksums, schemas, required fields, numeric ranges, and expected key uniqueness.
- Reconcile overview, chart, and detail totals under the same filters.
- Test board-specific windows, the low-volume job fallback, and visible period labels.
- Test missing, stale, failed, partial, and empty states.
- Test that author and comment interpretations never merge.
- Test filters, source links, and layout at supported screen sizes.
- Keep semantic panels disabled until their required source fields and freshness metadata exist.

## Phased Delivery

### Release 1: factual dashboard

Deliver navigation, current rankings, engagement views, representative titles, sample coverage, and collection health from the production archive.

### Release 2: semantic dashboard

Add bodies, comments, topics, intent, sentiment, comment reactions, confidence, and semantic freshness.

### Release 3: movement and diffusion

Add aligned snapshot history, 24-hour, 7-day, and 30-day movement, rising signals, and cross-board issue diffusion.
