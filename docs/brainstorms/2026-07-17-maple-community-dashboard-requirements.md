---
date: 2026-07-17
topic: maple-community-dashboard
---

# Maple Community Dashboard Requirements

## Summary

Build a private two-level dashboard for MapleStory operations and planning teams. The overview surfaces material community signals, while board-specific workspaces apply analysis that matches each board's purpose.

---

## Problem Frame

Job boards, the free board, Q&A, and tips boards represent different user intents. A shared popularity or sentiment treatment would hide job-specific complaints, confuse questions with negative opinion, and overstate engagement as approval.

The current production export contains titles, engagement counters, cumulative rankings, and collection status. It does not contain post bodies, comment text, semantic labels, or enough snapshot history for sentiment and rising-trend analysis.

---

## Key Decisions

- **Two-level navigation.** Start with an operating overview and drill into board-specific analysis.
- **Board-specific windows.** Default to 24 hours for free, 7 days for jobs and Q&A, and 30 days for tips; low-volume jobs may expand to 30 days with a visible label.
- **Separate meaning layers.** Keep popularity separate from sentiment and analyze the author's position separately from comment reactions.
- **Phased evidence.** Ship engagement and collection-health views from the current export, then enable semantic panels when bodies, comments, and analysis labels exist.
- **Editorial visual language.** Use a restrained research-dashboard style with direct Korean labels and visible evidence.

---

## Requirements

**Navigation and overview**

- R1. The default view must summarize major issues, job-board complaint or request signals, free-board reactions, and data freshness.
- R2. Users must be able to move from every summary signal to its board, topic, job, and representative source posts.

**Job boards**

- R3. The job comparison view must cover all available jobs and show both absolute sample size and normalized rates.
- R4. Each job detail must separate topics, complaints, requests, questions, praise, and debate.
- R5. Each job detail must compare author sentiment with comment agreement, disagreement, added information, questions, jokes, and conflict.

**Non-job boards**

- R6. The free-board view must prioritize current issue share, movement, sentiment, controversy, and cross-board diffusion.
- R7. The Q&A view must prioritize repeated questions, knowledge gaps, and unresolved or low-response themes rather than positive-versus-negative ranking.
- R8. The tips view must prioritize useful information themes, engagement, freshness, and sustained interest.

**Trust and evidence**

- R9. Popularity metrics must never be presented as approval or positive sentiment.
- R10. Every semantic result must show its source period, sample size, analysis freshness, and confidence.
- R11. Missing, stale, partial, or low-sample data must remain visible as such and must not be silently replaced by older analysis.
- R12. Summaries must link to representative source posts without republishing full source content.
- R13. Dashboard totals, charts, and detail tables must reconcile to the same filtered data.

**Presentation**

- R14. The interface must avoid gradients, decorative AI motifs, excessive cards, and unsupported narrative summaries.
- R15. The primary visual forms must be ranked bars, heatmaps, comparison dots, trend lines, and evidence tables.

---

## Key Flows

- F1. **Overview to evidence**
  - **Trigger:** An operator sees a material issue or job signal.
  - **Steps:** Open the related workspace, inspect its breakdown, then follow a representative source link.
  - **Covered by:** R1, R2, R12.
- F2. **Degraded data**
  - **Trigger:** Collection, history, or semantic analysis is incomplete.
  - **Steps:** Keep factual engagement data available and replace unsupported semantic output with a clear unavailable or stale state.
  - **Covered by:** R10, R11, R13.
- F3. **Semantic expansion**
  - **Trigger:** Bodies, comments, and analysis labels become available.
  - **Steps:** Enable topic, intent, sentiment, and reaction panels without changing the established navigation model.
  - **Covered by:** R4-R8, R10.

---

## Acceptance Examples

- AE1. **Covers R3 and R11.** Given a job has too few 7-day posts, when its detail view opens, then the dashboard shows the sample warning and may expand to 30 days with the changed period visible.
- AE2. **Covers R5 and R9.** Given a negative author post receives mostly disagreeing comments, when it is summarized, then author sentiment and community reaction remain separate.
- AE3. **Covers R10 and R11.** Given semantic analysis is older than engagement collection, when the overview opens, then current engagement remains visible while semantic panels show their older freshness time.

---

## Success Criteria

- An operations or planning reader can identify the leading current issue and reach supporting posts within one minute.
- A reader can compare jobs without mistaking larger board volume for a worse reaction rate.
- No semantic statement appears without source period, sample size, freshness, and confidence.
- The current metadata export produces a useful first release without fabricated sentiment or trend claims.

---

## Scope Boundaries

- The first release does not infer reliable sentiment from titles alone.
- The first release does not claim 24-hour, 7-day, or 30-day movement without historical metric snapshots.
- Public sharing and external-facing presentation are outside the current private internal scope.

---

## Dependencies and Assumptions

- The current source is `exports/production-20260716-190257.zip`.
- Semantic analysis depends on future body, comment, topic, sentiment, reaction, and confidence exports.
- Rising analysis depends on aligned historical snapshots rather than latest-value rows.
- Source periods and low-sample thresholds remain configurable and visible.

---

## Sources

- `docs/superpowers/specs/2026-07-14-maple-inven-monitoring-design.md`
- `docs/superpowers/plans/2026-07-14-maple-inven-monitoring-implementation.md`
- `CONCEPTS.md`
