from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from maple_monitor.collection.types import PostListItem
from maple_monitor.config import CollectionSettings
from maple_monitor.sources import SourceDefinition


@dataclass(frozen=True)
class IncrementalScanResult:
    items: tuple[PostListItem, ...]
    pages_fetched: int
    boundary_reached: bool
    high_water_post_id: int | None
    status: Literal["succeeded", "partial"]


def scan_incremental_pages(
    source: SourceDefinition,
    prior_high_water: int | None,
    settings: CollectionSettings,
    *,
    fetch_page: Callable[[int, int], bytes],
    parse_page: Callable[[int, bytes, datetime], list[PostListItem]],
    fetched_at: Callable[[], datetime],
    wait_between_pages: Callable[[], None],
) -> IncrementalScanResult:
    accepted: dict[tuple[int, int], tuple[tuple[int, int, int, int], PostListItem]] = {}
    boundary_page: int | None = None
    greatest_ordinary_id: int | None = None
    pages_fetched = 0

    for page in range(1, settings.incremental_max_pages + 1):
        if page > 1:
            wait_between_pages()
        page_items = parse_page(source.board_id, fetch_page(source.board_id, page), fetched_at())
        pages_fetched = page
        for order, item in enumerate(page_items):
            key = (item.board_id, item.post_id)
            preference = (item.views, item.recommendations, item.comments, page * 10_000 + order)
            if key not in accepted or preference > accepted[key][0]:
                accepted[key] = (preference, item)
            if not item.is_notice and not item.is_ad:
                greatest_ordinary_id = (
                    item.post_id
                    if greatest_ordinary_id is None
                    else max(greatest_ordinary_id, item.post_id)
                )
                if (
                    prior_high_water is not None
                    and boundary_page is None
                    and item.post_id <= prior_high_water
                ):
                    boundary_page = page

        minimum_done = page >= settings.incremental_min_pages
        if prior_high_water is None and minimum_done:
            break
        if (
            boundary_page is not None
            and minimum_done
            and page >= boundary_page + settings.incremental_overlap_pages
        ):
            break

    boundary_reached = prior_high_water is None or (
        boundary_page is not None
        and pages_fetched >= boundary_page + settings.incremental_overlap_pages
    )
    status: Literal["succeeded", "partial"] = "succeeded" if boundary_reached else "partial"
    high_water = greatest_ordinary_id if boundary_reached else prior_high_water
    return IncrementalScanResult(
        items=tuple(value[1] for value in accepted.values()),
        pages_fetched=pages_fetched,
        boundary_reached=boundary_reached,
        high_water_post_id=high_water,
        status=status,
    )
