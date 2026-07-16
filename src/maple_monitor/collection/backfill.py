from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from maple_monitor.collection.client import ListPageClientError
from maple_monitor.collection.parser import InvalidSourcePage
from maple_monitor.collection.repository import SnapshotConfigConflict
from maple_monitor.collection.service import collect_board_slot
from maple_monitor.collection.types import PostListItem
from maple_monitor.config import LoadedSettings
from maple_monitor.db import session_scope
from maple_monitor.models import SourceBackfillState
from maple_monitor.sources import SOURCES, SourceDefinition


@dataclass(frozen=True)
class BackfillBudgetSummary:
    pages_fetched: int
    accepted: int
    failed_sources: tuple[str, ...]


_SAFE_PAGE_ERRORS = (
    InvalidSourcePage,
    ListPageClientError,
    OSError,
    SQLAlchemyError,
    SnapshotConfigConflict,
)


def _initial_cursors(
    engine: Engine,
    sources: Sequence[SourceDefinition],
) -> dict[str, tuple[SourceDefinition, int]]:
    cursors: dict[str, tuple[SourceDefinition, int]] = {}
    with session_scope(engine) as session:
        for source in sources:
            session.execute(
                insert(SourceBackfillState)
                .values(source_key=source.key, next_page=3)
                .on_conflict_do_nothing(index_elements=[SourceBackfillState.source_key])
            )
        session.flush()
        states = {
            state.source_key: state
            for state in session.scalars(
                select(SourceBackfillState).where(
                    SourceBackfillState.source_key.in_([source.key for source in sources])
                )
            )
        }
        for source in sources:
            state = states[source.key]
            if not state.complete:
                cursors[source.key] = (source, max(1, state.next_page - 1))
    return cursors


def _window_items(
    items: list[PostListItem],
    cutoff: datetime,
) -> tuple[tuple[PostListItem, ...], bool, int | None]:
    accepted: list[PostListItem] = []
    complete = False
    checkpoint: int | None = None
    for item in items:
        if not item.is_notice and not item.is_ad:
            checkpoint = item.post_id
            if item.published_at < cutoff:
                complete = True
                break
        accepted.append(item)
    return tuple(accepted), complete, checkpoint


def run_backfill_budget(
    engine: Engine,
    slot: datetime,
    loaded_settings: LoadedSettings,
    *,
    fetch_page: Callable[[int, int], bytes],
    parse_page: Callable[[int, bytes, datetime], list[PostListItem]],
    fetched_at: Callable[[], datetime],
    wait_between_pages: Callable[[], None],
    sources: Sequence[SourceDefinition] = SOURCES,
    page_budget: int | None = None,
) -> BackfillBudgetSummary:
    """Spend one bounded, round-robin backfill budget with per-page commits."""

    configured_budget = loaded_settings.settings.collection.backfill_page_budget_per_cycle
    budget = configured_budget if page_budget is None else page_budget
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
        raise ValueError("page_budget must be a nonnegative integer")
    budget = min(budget, configured_budget)
    cutoff = slot - timedelta(days=loaded_settings.settings.ranking.window_days)
    cursors = _initial_cursors(engine, sources)
    pages_fetched = 0
    total_accepted = 0
    failed: list[str] = []

    while cursors and pages_fetched < budget:
        for source_key in tuple(cursors):
            if pages_fetched >= budget:
                break
            source, page = cursors[source_key]
            if pages_fetched:
                wait_between_pages()
            pages_fetched += 1
            try:
                actual = fetched_at()
                items = parse_page(source.board_id, fetch_page(source.board_id, page), actual)
                accepted_items, complete, checkpoint = _window_items(items, cutoff)
                with session_scope(engine) as session:
                    state = session.scalar(
                        select(SourceBackfillState)
                        .where(SourceBackfillState.source_key == source.key)
                        .with_for_update()
                    )
                    assert state is not None
                    collection = collect_board_slot(
                        session,
                        source.board_id,
                        accepted_items,
                        slot,
                        loaded_settings,
                        fetched_at=actual,
                    )
                    state.next_page = page + 1
                    state.checkpoint_post_id = checkpoint
                    state.complete = complete
                    state.updated_at = actual
                    accepted_count = collection.inserted + collection.updated
                total_accepted += accepted_count
            except _SAFE_PAGE_ERRORS:
                failed.append(source.key)
                del cursors[source_key]
                continue

            if complete:
                del cursors[source_key]
            else:
                cursors[source_key] = (source, page + 1)

    return BackfillBudgetSummary(pages_fetched, total_accepted, tuple(failed))
