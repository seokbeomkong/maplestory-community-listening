# Production Metadata Collection Design

## Goal

Run a low-resource production collector on the VPS that accumulates complete, replay-safe Maple Inven metadata. The laptop downloads this metadata and decides which posts require detailed collection and preprocessing; LLM analysis remains a separate final stage.

## Scope

The first production registry contains eight public sources:

| Source key | Board | Board ID | Kind | Analysis unit |
| --- | --- | ---: | --- | --- |
| `warrior` | 전사 | 2294 | job | normalized job category |
| `magician` | 마법사 | 2295 | job | normalized job category |
| `archer` | 궁수 | 2296 | job | normalized job category |
| `thief` | 도적 | 2297 | job | normalized job category |
| `pirate` | 해적 | 2298 | job | normalized job category |
| `free` | 자유 게시판 | 5974 | free | `free` |
| `qna` | 질문과 답변 | 2300 | info | `qna` |
| `tips` | 팁과 노하우 | 2304 | info | `tips` |

Job-board rows whose normalized category is `팁/정보`, `핑크빈`, or `예티` are excluded. Notices and advertisements do not establish collection boundaries and do not enter rankings. Security and private-network expansion are outside this slice; existing safe parsing and title quarantine behavior remain unchanged.

The VPS stores metadata only: board identity, post identity, normalized analysis unit, title, publication time, source URL, current category, observation slot and actual time, views, recommendations, and comment count. It does not fetch post bodies, comment text, images, video, attachments, or invoke an LLM.

## Collection Strategy

### Adaptive six-hour incremental collection

Each source is collected independently at the configured six-hour KST slot. Before fetching, the collector reads that source's highest previously committed non-notice post ID as its high-water mark.

The collector starts at page 1 and fetches at least `incremental_min_pages` pages. It continues until a non-notice post at or below the prior high-water mark is observed, then fetches `incremental_overlap_pages` additional pages. Consequently, more than two pages are fetched whenever more than two pages of new posts arrived between slots.

The default operator settings are:

- `incremental_min_pages: 2`
- `incremental_overlap_pages: 1`
- `incremental_max_pages: 100`
- `backfill_page_budget_per_cycle: 40`
- existing randomized request delay: 1.5 to 3.0 seconds

The maximum is a runaway guard, not a normal stopping condition. Reaching it before the old boundary marks that source run `partial`, does not advance its successful boundary, and suppresses backfill for that source. The next attempt scans from page 1 again. Notices, deletions, and page movement cannot create a successful false boundary because any ordinary post ID at or below the prior high-water mark is sufficient and the overlap pages are still collected.

On a source's first run, no prior boundary exists. The collector commits the configured minimum pages as the immediate recent baseline and records the newest ordinary post as its high-water mark. Older posts are filled by backfill.

### Progressive 90-day backfill

After all incremental source scans have had priority, the cycle spends at most `backfill_page_budget_per_cycle` additional page requests on round-robin backfill. Backfill progress is persisted, overlaps the previous checkpoint page, and relies on the same database upserts so retries are harmless. It stops a source after ordinary posts older than the moving 90-day window are observed.

Backfill never delays or replaces a due incremental scan. A failed or restarted backfill resumes from its last committed checkpoint. Historical counters represent the value visible when the post was backfilled; only future six-hour observations can produce true counter deltas.

## Persistence and Idempotency

Each source-slot has an independent run identity such as `metadata:warrior`. PostgreSQL advisory locking and the existing run ledger prevent concurrent duplicate work. A source is committed independently so one failed source cannot roll back successful sources.

The existing snapshot key `(board_id, post_id, observed_at_slot_kst)` remains the idempotency boundary. Replaying a slot uses monotonic metric upserts and cannot duplicate a post or snapshot. Rankings refresh after the cycle from all successfully committed source data. A cycle summary reports succeeded, partial, failed, busy, and already-succeeded source counts.

Backfill progress has a dedicated per-source state containing the next estimated page, overlap checkpoint, completion state, and last update time. The state advances only in the same transaction as its accepted metadata.

## VPS, Laptop, and LLM Boundaries

1. **VPS:** fetch public list pages, parse metadata, persist snapshots, maintain cumulative rankings, and export raw CSV files.
2. **Laptop:** download exports, calculate six-hour/day/week/month deltas and weighted rising scores, select cumulative and rising top-50 candidates, then fetch or queue detailed bodies and comments in a later slice.
3. **LLM:** analyze only locally selected and preprocessed text in a later slice. No scraped text can direct VPS operations.

The production CSV export must include all registered sources without changing the one-command laptop download contract.

## Resource Controls

Collection remains sequential with concurrency 1. Incremental work always precedes backfill, all page budgets and delays are operator-managed settings, and the existing Docker CPU, memory, log, database, and retry limits remain in force. No browser automation or Codex token usage is required for scheduled VPS collection.

## Error Handling and Observability

- Network or parse failure is isolated to the affected source.
- A failed source does not advance its boundary or backfill checkpoint.
- Re-execution of the same source-slot is safe.
- A source that hits the incremental page guard is visibly `partial`, not `succeeded`.
- Cycle diagnostics include pages requested, items accepted/excluded, boundary reached, backfill progress, and per-source status without storing upstream response bodies or secrets.
- Collector health requires a recent cycle with at least one successfully collected source and reports partial/failed source counts in logs.

## Testing and Acceptance

Implementation follows test-first development. Fixtures cover more than two pages of new posts, a deleted prior high-water post, notices with old IDs, excluded job categories, a page-guard partial result, independent source failure, replay of the same slot, and resumable backfill.

Production acceptance requires:

1. all eight sources appear in the registry and database;
2. a live manual cycle completes without stopping on one source failure;
3. a second execution of the same slot creates no duplicate snapshots;
4. scheduled collection remains healthy under the VPS resource limits;
5. a downloaded export contains multiple job groups plus free, Q&A, and tips metadata with valid checksums.
