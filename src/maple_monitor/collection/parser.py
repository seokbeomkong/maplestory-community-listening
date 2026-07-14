from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Final
from urllib.parse import SplitResult, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

from maple_monitor.collection.types import PostListItem


MAX_LIST_PAGE_BYTES: Final = 512_000
SUPPORTED_BOARD_ID: Final = 2294
SUPPORTED_CATEGORY: Final = "히어로"
SUPPORTED_ANALYSIS_UNIT: Final = "hero"
CANONICAL_HOST: Final = "www.inven.co.kr"
KST: Final = ZoneInfo("Asia/Seoul")

_REQUIRED_HEADERS: Final = {
    "제목": "title",
    "등록일": "date",
    "조회": "views",
    "추천": "recommendations",
}
_ARTICLE_PATH = re.compile(r"/board/maple/(?P<board>[0-9]+)/(?P<post>[0-9]+)\Z")
_COMMENT_SUFFIX = re.compile(r"\[(?P<count>[0-9][0-9,]*)]\s*\Z")
_CATEGORY_PREFIX = re.compile(r"^\[(?P<category>[^]]+)]\s*")
_INTEGER = re.compile(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)\Z")
_NOTICE_CLASSES: Final = frozenset({"notice", "notice-row"})
_AD_CLASSES: Final = frozenset({"ad", "ad-row", "advertisement"})


class InvalidSourcePage(ValueError):
    """Raised when a response is not the narrow supported list-page structure."""


def _normalized_text(node: Tag) -> str:
    return " ".join(node.get_text(" ", strip=True).split())


def _parse_nonnegative_integer(value: str, *, field: str) -> int:
    compact = value.strip()
    if len(compact) > 32 or _INTEGER.fullmatch(compact) is None:
        raise InvalidSourcePage(f"{field} metric is invalid")
    return int(compact.replace(",", ""))


def _find_board_table(soup: BeautifulSoup) -> tuple[Tag, dict[str, int]]:
    saw_header_candidate = False
    for table in soup.select("table"):
        labels = [_normalized_text(cell) for cell in table.select("thead th")]
        if not any(label in _REQUIRED_HEADERS for label in labels):
            continue
        saw_header_candidate = True
        if all(labels.count(label) == 1 for label in _REQUIRED_HEADERS):
            return table, {
                target: labels.index(label) for label, target in _REQUIRED_HEADERS.items()
            }
    if saw_header_candidate:
        raise InvalidSourcePage("required board header is missing or duplicated")
    raise InvalidSourcePage("expected board header is missing")


def _article_identity(raw_href: object, expected_board: int) -> tuple[int, str]:
    if not isinstance(raw_href, str) or not raw_href or len(raw_href) > 2_048:
        raise InvalidSourcePage("article URL is invalid")
    if raw_href != raw_href.strip() or any(character.isspace() for character in raw_href):
        raise InvalidSourcePage("article URL is invalid")

    try:
        parsed: SplitResult = urlsplit(raw_href)
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
        port = parsed.port
    except (UnicodeError, ValueError):
        raise InvalidSourcePage("article URL is invalid") from None
    if parsed.fragment:
        raise InvalidSourcePage("article URL is invalid")
    if parsed.scheme or parsed.netloc:
        if (
            parsed.scheme != "https"
            or hostname != CANONICAL_HOST
            or username is not None
            or password is not None
        ):
            raise InvalidSourcePage("article URL is invalid")
        if port not in (None, 443):
            raise InvalidSourcePage("article URL is invalid")
    elif not raw_href.startswith("/") or raw_href.startswith("//"):
        raise InvalidSourcePage("article URL is invalid")

    match = _ARTICLE_PATH.fullmatch(parsed.path)
    if match is None or int(match["board"]) != expected_board:
        raise InvalidSourcePage("article URL does not match the supported board")
    post_id = int(match["post"])
    if not 1 <= post_id <= 2**63 - 1:
        raise InvalidSourcePage("article URL has an invalid post identity")
    return post_id, f"https://{CANONICAL_HOST}/board/maple/{expected_board}/{post_id}"


def _extract_category(title_cell: Tag, anchor: Tag) -> str:
    category_node = title_cell.select_one(".category, .cate")
    if category_node is not None:
        category = _normalized_text(category_node).strip("[]").strip()
    else:
        match = _CATEGORY_PREFIX.match(_normalized_text(anchor))
        category = match["category"].strip() if match is not None else ""
    if category != SUPPORTED_CATEGORY:
        raise InvalidSourcePage("article category is missing or unsupported")
    return category


def _extract_title_and_comments(title_cell: Tag, anchor: Tag) -> tuple[str, int]:
    title = _normalized_text(anchor)
    title = _CATEGORY_PREFIX.sub("", title, count=1)
    marker = title_cell.select_one(".comment, .cnt, .comment-count")
    comments = (
        _parse_nonnegative_integer(_normalized_text(marker).strip("[]"), field="comment")
        if marker is not None
        else 0
    )
    suffix = _COMMENT_SUFFIX.search(title)
    if suffix is not None:
        comments = max(
            comments,
            _parse_nonnegative_integer(suffix["count"], field="comment"),
        )
        title = title[: suffix.start()].rstrip()
    if not title:
        raise InvalidSourcePage("article title is missing")
    return title, comments


def _parse_source_time(value: str, fetched_at: datetime) -> datetime:
    local = fetched_at.astimezone(KST)
    try:
        explicit_date = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        pass
    else:
        return explicit_date.replace(tzinfo=KST)

    month_day = re.fullmatch(r"(?P<month>[0-9]{2})-(?P<day>[0-9]{2})", value)
    if month_day is not None:
        month = int(month_day["month"])
        day = int(month_day["day"])
        try:
            datetime(2000, month, day)
        except ValueError:
            raise InvalidSourcePage("article date has an unsupported format") from None
        for years_ago in range(9):
            year = local.year - years_ago
            if year < 1:
                break
            try:
                candidate = datetime(year, month, day, tzinfo=KST)
            except ValueError:
                continue
            if candidate.date() <= local.date():
                return candidate
        raise InvalidSourcePage("article date has an unsupported format")

    try:
        parsed_time = datetime.strptime(value, "%H:%M")
    except ValueError:
        raise InvalidSourcePage("article date has an unsupported format") from None
    candidate = local.replace(
        hour=parsed_time.hour,
        minute=parsed_time.minute,
        second=0,
        microsecond=0,
    )
    if candidate > local:
        try:
            candidate -= timedelta(days=1)
        except OverflowError:
            raise InvalidSourcePage("article date has an unsupported format") from None
    return candidate


def _row_kind(row: Tag, title_cell: Tag) -> tuple[bool, bool]:
    classes = {str(value).lower() for value in row.get("class", [])}
    label = title_cell.select_one(".row-label, .label")
    label_text = _normalized_text(label) if label is not None else ""
    is_notice = bool(classes & _NOTICE_CLASSES) or label_text == "공지"
    is_ad = bool(classes & _AD_CLASSES) or label_text == "광고"
    if is_notice and is_ad:
        raise InvalidSourcePage("article row kind is ambiguous")
    return is_notice, is_ad


def _parse_article_row(
    row: Tag,
    columns: dict[str, int],
    board_id: int,
    fetched_at: datetime,
) -> PostListItem | None:
    cells = row.find_all("td", recursive=False)
    if not cells:
        return None
    if len(cells) <= max(columns.values()):
        raise InvalidSourcePage("article row has fewer cells than its header")

    title_cell = cells[columns["title"]]
    anchors = title_cell.select("a[href]")
    article_anchors = [
        anchor for anchor in anchors if "/board/maple/" in str(anchor.get("href", ""))
    ]
    if not article_anchors:
        if anchors:
            raise InvalidSourcePage("article URL is invalid")
        return None
    if len(article_anchors) != 1:
        raise InvalidSourcePage("article URL is ambiguous")
    anchor = article_anchors[0]
    post_id, source_url = _article_identity(anchor.get("href"), board_id)
    category = _extract_category(title_cell, anchor)
    title, comments = _extract_title_and_comments(title_cell, anchor)
    is_notice, is_ad = _row_kind(row, title_cell)

    return PostListItem(
        board_id=board_id,
        post_id=post_id,
        analysis_unit=SUPPORTED_ANALYSIS_UNIT,
        category=category,
        title=title,
        published_at=_parse_source_time(_normalized_text(cells[columns["date"]]), fetched_at),
        views=_parse_nonnegative_integer(_normalized_text(cells[columns["views"]]), field="view"),
        recommendations=_parse_nonnegative_integer(
            _normalized_text(cells[columns["recommendations"]]),
            field="recommendation",
        ),
        comments=comments,
        source_url=source_url,
        is_notice=is_notice,
        is_ad=is_ad,
    )


def parse_list_page(board_id: int, html: bytes, fetched_at: datetime) -> list[PostListItem]:
    if (
        isinstance(board_id, bool)
        or not isinstance(board_id, int)
        or board_id != SUPPORTED_BOARD_ID
    ):
        raise InvalidSourcePage("unsupported board")
    if not isinstance(fetched_at, datetime) or fetched_at.tzinfo is None:
        raise ValueError("fetched_at must be a timezone-aware datetime")
    try:
        offset = fetched_at.utcoffset()
    except (OverflowError, TypeError, ValueError):
        raise ValueError("fetched_at must be representable in KST") from None
    if offset is None:
        raise ValueError("fetched_at must be a timezone-aware datetime")
    try:
        fetched_at.astimezone(KST)
    except (OverflowError, ValueError):
        raise ValueError("fetched_at must be representable in KST") from None
    if not isinstance(html, bytes):
        raise TypeError("html must be bytes")
    if not html:
        raise InvalidSourcePage("source page is empty")
    if len(html) > MAX_LIST_PAGE_BYTES:
        raise InvalidSourcePage("source page exceeds the size limit")
    try:
        decoded = html.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise InvalidSourcePage("source page is not valid UTF-8") from exc

    soup = BeautifulSoup(decoded, "lxml")
    table, columns = _find_board_table(soup)
    items = [
        item
        for row in table.select("tbody tr")
        if (item := _parse_article_row(row, columns, board_id, fetched_at)) is not None
    ]
    if not items:
        raise InvalidSourcePage("no canonical article rows found")
    return items
