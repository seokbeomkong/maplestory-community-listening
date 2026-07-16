from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from maple_monitor.collection.pagination import scan_incremental_pages
from maple_monitor.collection.types import PostListItem
from maple_monitor.config import CollectionSettings
from maple_monitor.sources import source_for_board


FETCHED_AT = datetime(2026, 7, 16, 12, tzinfo=UTC)
SOURCE = source_for_board(2294)


def _settings(*, max_pages: int = 100) -> CollectionSettings:
    return CollectionSettings(
        interval_hours=6,
        slot_minute_kst=20,
        request_min_delay_seconds=1.5,
        request_max_delay_seconds=3.0,
        concurrency=1,
        max_retries=3,
        incremental_min_pages=2,
        incremental_overlap_pages=1,
        incremental_max_pages=max_pages,
        backfill_page_budget_per_cycle=40,
    )


def _item(
    post_id: int,
    *,
    views: int = 10,
    recommendations: int = 2,
    comments: int = 1,
    is_notice: bool = False,
    is_ad: bool = False,
) -> PostListItem:
    return PostListItem(
        board_id=SOURCE.board_id,
        post_id=post_id,
        analysis_unit="hero",
        category="hero",
        title=f"post {post_id}",
        published_at=FETCHED_AT,
        views=views,
        recommendations=recommendations,
        comments=comments,
        source_url=f"https://www.inven.co.kr/board/maple/{SOURCE.board_id}/{post_id}",
        is_notice=is_notice,
        is_ad=is_ad,
    )


def _scan(
    pages: dict[int, list[PostListItem]],
    *,
    prior_high_water: int | None,
    settings: CollectionSettings | None = None,
):
    fetched_pages: list[int] = []
    waits: list[None] = []

    def fetch_page(board_id: int, page: int) -> bytes:
        assert board_id == SOURCE.board_id
        fetched_pages.append(page)
        return str(page).encode()

    def parse_page(
        board_id: int,
        body: bytes,
        fetched_at: datetime,
    ) -> list[PostListItem]:
        assert board_id == SOURCE.board_id
        assert fetched_at == FETCHED_AT
        return pages[int(body)]

    result = scan_incremental_pages(
        SOURCE,
        prior_high_water,
        settings or _settings(),
        fetch_page=fetch_page,
        parse_page=parse_page,
        fetched_at=lambda: FETCHED_AT,
        wait_between_pages=lambda: waits.append(None),
    )
    return result, fetched_pages, waits


def test_first_run_fetches_exactly_the_minimum_two_pages() -> None:
    pages = {
        1: [_item(999, is_notice=True), _item(200)],
        2: [_item(998, is_ad=True), _item(199)],
    }

    result, fetched_pages, waits = _scan(pages, prior_high_water=None)

    assert fetched_pages == [1, 2]
    assert len(waits) == 1
    assert result.pages_fetched == 2
    assert result.boundary_reached is True
    assert result.high_water_post_id == 200
    assert result.status == "succeeded"
    assert [item.post_id for item in result.items] == [999, 200, 998, 199]


def test_boundary_on_page_four_fetches_one_overlap_page() -> None:
    pages = {
        1: [_item(140)],
        2: [_item(130)],
        3: [_item(120)],
        4: [_item(100)],
        5: [_item(99)],
    }

    result, fetched_pages, waits = _scan(pages, prior_high_water=100)

    assert fetched_pages == [1, 2, 3, 4, 5]
    assert len(waits) == 4
    assert result.pages_fetched == 5
    assert result.boundary_reached is True
    assert result.high_water_post_id == 140
    assert result.status == "succeeded"


@pytest.mark.parametrize("special_kind", ["notice", "ad"])
def test_special_rows_do_not_establish_boundary_or_advance_high_water(
    special_kind: str,
) -> None:
    special_flags = {f"is_{special_kind}": True}
    pages = {
        1: [_item(999, **special_flags), _item(1, **special_flags), _item(110)],
        2: [_item(109)],
        3: [_item(100)],
        4: [_item(99)],
    }

    result, fetched_pages, _ = _scan(pages, prior_high_water=100)

    assert fetched_pages == [1, 2, 3, 4]
    assert result.boundary_reached is True
    assert result.high_water_post_id == 110


def test_any_ordinary_id_at_or_below_a_deleted_prior_high_water_is_the_boundary() -> None:
    pages = {
        1: [_item(105)],
        2: [_item(102)],
        3: [_item(99)],
        4: [_item(98)],
    }

    result, fetched_pages, _ = _scan(pages, prior_high_water=100)

    assert fetched_pages == [1, 2, 3, 4]
    assert result.boundary_reached is True
    assert result.high_water_post_id == 105


def test_duplicate_page_edge_rows_collapse_without_changing_first_seen_order() -> None:
    initial = _item(105, views=10, recommendations=10, comments=10)
    lower_priority = replace(initial, views=9, recommendations=999, comments=999)
    latest_equal = replace(initial, title="latest equal observation")
    pages = {
        1: [initial, _item(104)],
        2: [lower_priority, latest_equal, _item(103)],
    }

    result, _, _ = _scan(pages, prior_high_water=None)

    assert [item.post_id for item in result.items] == [105, 104, 103]
    assert result.items[0] == latest_equal


def test_page_guard_partial_preserves_prior_high_water() -> None:
    pages = {page: [_item(1_000 - page)] for page in range(1, 101)}

    result, fetched_pages, waits = _scan(pages, prior_high_water=1)

    assert fetched_pages == list(range(1, 101))
    assert len(waits) == 99
    assert result.pages_fetched == 100
    assert result.boundary_reached is False
    assert result.high_water_post_id == 1
    assert result.status == "partial"


def test_boundary_at_page_guard_is_partial_when_overlap_cannot_be_fetched() -> None:
    prior_high_water = 500
    pages = {page: [_item(700 - page)] for page in range(1, 100)}
    pages[100] = [_item(prior_high_water)]

    result, fetched_pages, waits = _scan(pages, prior_high_water=prior_high_water)

    assert fetched_pages == list(range(1, 101))
    assert len(waits) == 99
    assert result.pages_fetched == 100
    assert result.boundary_reached is False
    assert result.high_water_post_id == prior_high_water
    assert result.status == "partial"
