# Local semantic analysis pipeline design

## Objective

Turn each verified production metadata export into a reproducible, company-facing portfolio
dashboard that explains what MapleStory users are discussing and how they react. The dashboard
must show only observed metrics or completed model output. It must not contain assistant-facing
copy, implementation disclaimers, or claims based on metadata alone.

## Source and analysis periods

The production ZIP remains the immutable source of post identity, publication time, board/job,
URL, views, recommendations, and comment count. Every page derives and displays the exact
publication range of the rows used by that page. The archive-wide range and a filtered analysis
range are distinct: a 90-day view displays its actual first and last publication dates even if the
archive also contains older rows.

## Derived artifact boundary

Text collection and model output are stored outside the verified ZIP under an analysis directory
keyed by the ZIP filename and SHA-256 digest. The artifact contains a manifest, selected post
records, sanitized comment records, post-level labels, and aggregate summaries. The dashboard
loads an artifact only when its source digest and schema version match the selected ZIP.

This boundary preserves the export checksum contract, supports replay, and prevents stale model
results from being attached to a newer metadata snapshot.

## Selection and collection

For each analysis unit, select the highest-ranking post for comments, recommendations, and views
within the rolling 90-day window, then de-duplicate by `(board_id, post_id)`. Exclude notices when
the source exposes that state and cap the batch deterministically. This provides coverage across
all jobs and non-job boards without treating the entire archive as a deep-crawl target.

Fetch each selected public Inven article with one bounded HTTP client and a 1.5–3.0 second delay.
Parse the title and `#powerbbsContent` body, then request the public comment JSON endpoint used by
the page. Remove markup, author identifiers, profile data, and image-only comments. Preserve only
comment identity, parent identity, timestamp, sanitized text, and reaction counters. Validate the
reported comment count and mark incomplete responses rather than presenting them as complete.

All body and comment text passes the existing prompt-injection/security scanner. Quarantined text
is excluded from analysis and excerpts while its count remains auditable in the manifest.

## Model and labels

The first executable model is a deterministic Korean domain baseline, versioned with its lexicon
and preprocessing configuration. It separately labels:

- author intent: complaint, request, debate, question, praise, or information;
- topic: balance/skill, bug/usability, progression/reward, boss/combat, economy/auction,
  event/cash, operation/communication, or community;
- body sentiment and comment reaction: positive, neutral, negative, or mixed;
- confidence and the evidence terms or sentences that produced the label.

Post sentiment and comment reaction are never combined into one score. Engagement counters remain
features for sampling and prioritization, not sentiment labels. Low-confidence or conflicting
cases are exported as a bounded review queue for a Korean language model. Reviewed output must
carry model name, prompt version, input hash, label confidence, and evidence; unchanged hashes are
not submitted again.

The portfolio identifies the currently displayed provider and version. A future fine-tuned Korean
encoder replaces the baseline only after a time-split holdout demonstrates better macro-F1 and
calibration on a double-labeled gold set.

## Dashboard narrative

The project page opens with the problem statement: detect MapleStory community reactions soon
enough to support product and live-operations decisions. A visual five-stage flow shows metadata
collection, engagement-based selection, body/comment enrichment, model inference and validation,
and dashboard publication.

Job boards emphasize complaint/request/debate mix, topic distribution, body-versus-comment
reaction, sample size, and representative evidence. Free board emphasizes issue share and reaction
distribution. Q&A emphasizes recurring questions and response coverage. Tips emphasizes useful
information themes and engagement. Each section displays the exact source period, analyzed-post
count, analyzed-comment count, model version, and last analysis time.

Assistant-facing phrases such as “not yet executed,” “data unavailable,” “recruitment-linked
deliverable,” or directions to the dashboard author do not appear in portfolio pages. When no
matching semantic artifact exists, semantic sections are omitted; operational diagnostics remain
on the private collection-status page.

## Refresh lifecycle

1. VPS metadata collection runs every six hours at minute 20 KST.
2. The user downloads a new `production-*.zip` into the local export directory.
3. The local refresh command detects a new ZIP digest and runs only missing detail and inference
   work, reusing cached content hashes.
4. A complete artifact is written atomically after schema and reconciliation checks.
5. The Streamlit watcher detects the new artifact within 30 seconds and reruns the page.
6. Model retraining is separate: monthly or when drift/error thresholds trigger it, never for every
   ZIP.

## Failure behavior

- A partial download is ignored because it does not match the production ZIP pattern or fails ZIP
  validation.
- Fetch and parse failures are recorded per post and do not erase valid prior artifacts.
- Comment-count mismatches set `comments_complete=false` and exclude coverage claims.
- Invalid, quarantined, or digest-mismatched artifacts never reach portfolio insight panels.
- Model failures leave metadata views available and surface only in the operations page.

## Verification

- Unit tests cover deterministic selection, body and comment parsing, text normalization,
  quarantine exclusion, sentiment/intent/topic labels, digest identity, and period formatting.
- Dashboard tests assert the absence of meta copy and the presence of source period, model version,
  sample sizes, workflow stages, and actual semantic results from a fixture artifact.
- A bounded live smoke test verifies one article and its public comments without writing upstream.
- Full tests, lint, an actual analysis run, and one browser screenshot are required before handoff.
