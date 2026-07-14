from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from maple_monitor.collection.parser import (
    MAX_LIST_PAGE_BYTES,
    InvalidSourcePage,
    parse_list_page,
)
from maple_monitor.collection.types import PostListItem


KST = ZoneInfo("Asia/Seoul")
FETCHED_AT = datetime(2026, 7, 14, 6, 20, tzinfo=KST)


def _page(
    *,
    href: str = "/board/maple/2294/900010",
    headers: tuple[str, ...] = ("번호", "제목", "등록일", "조회", "추천"),
    cells: tuple[str, ...] | None = None,
) -> bytes:
    values = cells or (
        "900010",
        f'<span class="category">히어로</span><a href="{href}">검증 제목 [3]</a>',
        "06:10",
        "1,005",
        "4",
    )
    header_html = "".join(f"<th>{value}</th>" for value in headers)
    cell_html = "".join(f"<td>{value}</td>" for value in values)
    return (
        '<!doctype html><html lang="ko"><body><table class="board-list">'
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody><tr>{cell_html}</tr></tbody>"
        "</table></body></html>"
    ).encode()


def test_parses_sanitized_fixture_identity_metrics_and_row_kinds() -> None:
    items = parse_list_page(
        2294,
        Path("tests/fixtures/list_warrior.html").read_bytes(),
        FETCHED_AT,
    )

    assert all(isinstance(item, PostListItem) for item in items)
    assert [(item.post_id, item.is_notice, item.is_ad) for item in items] == [
        (900003, True, False),
        (900002, False, False),
        (900001, False, True),
    ]
    normal = items[1]
    assert normal.board_id == 2294
    assert normal.analysis_unit == "hero"
    assert normal.category == "히어로"
    assert normal.title == "장비 조합 기록"
    assert normal.published_at == datetime(2026, 7, 14, 6, 15, tzinfo=KST)
    assert (normal.views, normal.recommendations, normal.comments) == (1234, 9, 12)
    assert normal.source_url == "https://www.inven.co.kr/board/maple/2294/900002"
    assert items[2].source_url == "https://www.inven.co.kr/board/maple/2294/900001"


def test_finds_required_headers_when_columns_are_reordered() -> None:
    html = _page(
        headers=("추천", "등록일", "제목", "조회", "번호"),
        cells=(
            "4",
            "06:10",
            '<span class="category">히어로</span>'
            '<a href="/board/maple/2294/900010">검증 제목 [3]</a>',
            "1,005",
            "900010",
        ),
    )

    [item] = parse_list_page(2294, html, FETCHED_AT)

    assert (item.views, item.recommendations, item.comments) == (1005, 4, 3)
    assert item.title == "검증 제목"


@pytest.mark.parametrize(
    "href",
    [
        "/board/maple/9999/900010",
        "https://outside.example/board/maple/2294/900010",
        "https://www.inven.co.kr.attacker.example/board/maple/2294/900010",
        "https://[invalid]/board/maple/2294/900010",
        "https://www.inven.co.kr／board/maple/2294/900010",
        "//outside.example/board/maple/2294/900010",
        "https://user@www.inven.co.kr/board/maple/2294/900010",
        "/board/maple/2294/900010/forged",
    ],
)
def test_rejects_noncanonical_or_spoofed_article_hrefs(href: str) -> None:
    with pytest.raises(InvalidSourcePage, match="article URL"):
        parse_list_page(2294, _page(href=href), FETCHED_AT)


@pytest.mark.parametrize(
    "headers",
    [
        ("번호", "제목", "등록일", "조회"),
        ("번호", "제목", "제목", "등록일", "조회", "추천"),
    ],
)
def test_rejects_missing_or_duplicate_required_headers(headers: tuple[str, ...]) -> None:
    with pytest.raises(InvalidSourcePage, match="header"):
        parse_list_page(2294, _page(headers=headers), FETCHED_AT)


def test_ignores_an_unrelated_partial_header_table_before_the_board_table() -> None:
    valid_page = _page().decode()
    html = valid_page.replace(
        "<body>",
        "<body><table><thead><tr><th>제목</th></tr></thead></table>",
        1,
    ).encode()

    [item] = parse_list_page(2294, html, FETCHED_AT)

    assert item.post_id == 900010


def test_rejects_truncated_article_row() -> None:
    with pytest.raises(InvalidSourcePage, match="fewer cells"):
        parse_list_page(
            2294,
            _page(cells=("900010", '<a href="/board/maple/2294/900010">제목</a>')),
            FETCHED_AT,
        )


@pytest.mark.parametrize(
    "html",
    [b"", b"<!doctype html><html><body></body></html>"],
)
def test_rejects_empty_or_structurally_empty_page(html: bytes) -> None:
    with pytest.raises(InvalidSourcePage):
        parse_list_page(2294, html, FETCHED_AT)


def test_rejects_challenge_page_without_echoing_its_text() -> None:
    html = Path("tests/fixtures/challenge.html").read_bytes()

    with pytest.raises(InvalidSourcePage) as caught:
        parse_list_page(2294, html, FETCHED_AT)

    assert "요청을 처리할 수 없습니다" not in str(caught.value)


def test_rejects_page_above_input_bound() -> None:
    with pytest.raises(InvalidSourcePage, match="size limit"):
        parse_list_page(2294, b"x" * (MAX_LIST_PAGE_BYTES + 1), FETCHED_AT)


def test_rejects_non_utf8_source() -> None:
    with pytest.raises(InvalidSourcePage, match="UTF-8"):
        parse_list_page(2294, b"\xff\xfe", FETCHED_AT)


def test_rejects_unsupported_board_before_parsing() -> None:
    with pytest.raises(InvalidSourcePage, match="unsupported board"):
        parse_list_page(9999, _page(), FETCHED_AT)


def test_requires_timezone_aware_fetch_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_list_page(2294, _page(), datetime(2026, 7, 14, 6, 20))


def test_rejects_aware_fetch_time_outside_the_kst_datetime_range() -> None:
    with pytest.raises(ValueError, match="representable in KST"):
        parse_list_page(2294, _page(), datetime.max.replace(tzinfo=UTC))


@pytest.mark.parametrize(
    ("fetched_at", "source_value", "expected"),
    [
        (
            datetime(2026, 7, 14, 0, 10, tzinfo=KST),
            "23:59",
            datetime(2026, 7, 13, 23, 59, tzinfo=KST),
        ),
        (
            datetime(2026, 1, 1, 0, 10, tzinfo=KST),
            "12-31",
            datetime(2025, 12, 31, 0, 0, tzinfo=KST),
        ),
        (
            FETCHED_AT,
            "2025-12-31",
            datetime(2025, 12, 31, 0, 0, tzinfo=KST),
        ),
        (
            datetime(2024, 3, 1, 0, 10, tzinfo=KST),
            "02-29",
            datetime(2024, 2, 29, 0, 0, tzinfo=KST),
        ),
        (
            datetime(2025, 1, 1, 0, 10, tzinfo=KST),
            "02-29",
            datetime(2024, 2, 29, 0, 0, tzinfo=KST),
        ),
    ],
)
def test_resolves_today_time_date_and_year_rollover(
    fetched_at: datetime,
    source_value: str,
    expected: datetime,
) -> None:
    cells = (
        "900010",
        '<span class="category">히어로</span><a href="/board/maple/2294/900010">검증 제목</a>',
        source_value,
        "10",
        "1",
    )

    [item] = parse_list_page(2294, _page(cells=cells), fetched_at)

    assert item.published_at == expected
    assert item.published_at.tzinfo is KST
