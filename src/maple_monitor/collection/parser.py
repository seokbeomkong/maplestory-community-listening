from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from typing import Final
from urllib.parse import SplitResult, parse_qsl, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

from maple_monitor.collection.types import PostListItem
from maple_monitor.sources import SourceDefinition, analysis_unit_for, source_for_board


MAX_LIST_PAGE_BYTES: Final = 512_000
MAX_SOURCE_PAGE: Final = 100_000
SUPPORTED_CATEGORY: Final = "히어로"
CANONICAL_HOST: Final = "www.inven.co.kr"
KST: Final = ZoneInfo("Asia/Seoul")

_REQUIRED_HEADERS: Final = {
    "번호": "number",
    "제목": "title",
    "글쓴이": "author",
    "등록일": "date",
    "조회": "views",
    "추천": "recommendations",
}
_EXPECTED_CELL_CLASSES: Final = {
    "number": "num",
    "title": "tit",
    "author": "user",
    "date": "date",
    "views": "view",
    "recommendations": "reco",
}
_ARTICLE_PATH = re.compile(r"/board/maple/(?P<board>[0-9]+)/(?P<post>[0-9]+)\Z")
_CATEGORY_MARKER = re.compile(r"\[(?P<category>[^][\r\n]+)]\Z")
_COMMENT_MARKER = re.compile(r"\[(?P<count>(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+))]\Z")
_INTEGER = re.compile(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)\Z")
_SOURCE_PAGE = re.compile(r"[0-9]+\Z")
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
        if labels == list(_REQUIRED_HEADERS):
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
    if "#" in raw_href:
        raise InvalidSourcePage("article URL is invalid")
    if "?" in raw_href:
        try:
            query = parse_qsl(
                parsed.query,
                keep_blank_values=True,
                strict_parsing=True,
                encoding="utf-8",
                errors="strict",
                max_num_fields=1,
                separator="&",
            )
        except (UnicodeError, ValueError):
            raise InvalidSourcePage("article URL is invalid") from None
        if query != [("category", SUPPORTED_CATEGORY)]:
            if (
                len(query) != 1
                or query[0][0] != "p"
                or _SOURCE_PAGE.fullmatch(query[0][1]) is None
                or not 1 <= int(query[0][1]) <= MAX_SOURCE_PAGE
            ):
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


def _extract_category(title_cell: Tag, anchor: Tag) -> tuple[str, Tag]:
    category_nodes = title_cell.select("span.category")
    direct_anchor_categories = anchor.find_all("span", class_="category", recursive=False)
    if (
        len(category_nodes) != 1
        or len(direct_anchor_categories) != 1
        or category_nodes[0] is not direct_anchor_categories[0]
    ):
        raise InvalidSourcePage("article category marker is missing or ambiguous")
    category_node = direct_anchor_categories[0]
    marker = unicodedata.normalize("NFKC", category_node.get_text()).strip()
    match = _CATEGORY_MARKER.fullmatch(marker)
    if match is None:
        raise InvalidSourcePage("article category marker is invalid")
    category = match["category"].strip()
    return category, category_node


def _normalized_node_sequence(nodes: list[object]) -> str:
    values: list[str] = []
    for node in nodes:
        value = _normalized_text(node) if isinstance(node, Tag) else str(node).strip()
        if value:
            values.append(value)
    return " ".join(" ".join(values).split())


def _extract_title(anchor: Tag, category_node: Tag) -> str:
    children = list(anchor.children)
    if category_node in children:
        marker_index = children.index(category_node)
        if _normalized_node_sequence(children[:marker_index]):
            raise InvalidSourcePage("article category marker is not a title prefix")
        title = _normalized_node_sequence(children[marker_index + 1 :])
    elif anchor in category_node.parents:
        raise InvalidSourcePage("article category marker structure is invalid")
    else:
        title = _normalized_text(anchor)
    if not title:
        raise InvalidSourcePage("article title is missing")
    return title


def _extract_comments(text_wrap: Tag) -> int:
    markers = text_wrap.find_all("span", class_="con-comment", recursive=False)
    if len(markers) != 1:
        raise InvalidSourcePage("article comment marker is missing or ambiguous")
    value = _normalized_text(markers[0])
    if not value:
        return 0
    match = _COMMENT_MARKER.fullmatch(value)
    if match is None:
        raise InvalidSourcePage("article comment marker is invalid")
    return _parse_nonnegative_integer(match["count"], field="comment")


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
    source: SourceDefinition,
    fetched_at: datetime,
) -> tuple[bool, PostListItem | None]:
    board_id = source.board_id
    cells = row.find_all("td", recursive=False)
    if not cells:
        if _normalized_text(row):
            raise InvalidSourcePage("article row structure is unknown")
        return False, None
    if len(cells) < len(_REQUIRED_HEADERS):
        raise InvalidSourcePage("article row has fewer cells than its header")
    if len(cells) > len(_REQUIRED_HEADERS):
        raise InvalidSourcePage("article row has more cells than its header")

    for column, expected_class in _EXPECTED_CELL_CLASSES.items():
        cell_classes = {str(value).casefold() for value in cells[columns[column]].get("class", [])}
        if expected_class not in cell_classes:
            raise InvalidSourcePage("article cell structure is invalid")

    title_cell = cells[columns["title"]]
    text_wraps = title_cell.find_all("div", class_="text-wrap", recursive=False)
    if len(text_wraps) != 1:
        raise InvalidSourcePage("article title structure is missing or ambiguous")
    text_wrap = text_wraps[0]
    anchors = text_wrap.select("a.subject-link[href]")
    if len(anchors) != 1:
        raise InvalidSourcePage("article anchor is missing or ambiguous")
    anchor = anchors[0]
    article_links = [
        candidate
        for candidate in text_wrap.select("a[href]")
        if "/board/maple/" in str(candidate.get("href", ""))
    ]
    if article_links != [anchor]:
        raise InvalidSourcePage("article URL is ambiguous")
    post_id, source_url = _article_identity(anchor.get("href"), board_id)
    category, category_node = _extract_category(title_cell, anchor)
    title = _extract_title(anchor, category_node)
    comments = _extract_comments(text_wrap)
    is_notice, is_ad = _row_kind(row, title_cell)
    published_at = _parse_source_time(_normalized_text(cells[columns["date"]]), fetched_at)
    views = _parse_nonnegative_integer(
        _normalized_text(cells[columns["views"]]),
        field="view",
    )
    recommendations = _parse_nonnegative_integer(
        _normalized_text(cells[columns["recommendations"]]),
        field="recommendation",
    )
    analysis_unit = analysis_unit_for(source, category)
    if analysis_unit is None:
        return True, None

    return True, PostListItem(
        board_id=board_id,
        post_id=post_id,
        analysis_unit=analysis_unit,
        category=category,
        title=title,
        published_at=published_at,
        views=views,
        recommendations=recommendations,
        comments=comments,
        source_url=source_url,
        is_notice=is_notice,
        is_ad=is_ad,
    )


def parse_list_page(board_id: int, html: bytes, fetched_at: datetime) -> list[PostListItem]:
    try:
        source = source_for_board(board_id)
    except (TypeError, ValueError):
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
    items: list[PostListItem] = []
    validated_article_rows = 0
    for row in table.select("tbody tr"):
        is_article, item = _parse_article_row(row, columns, source, fetched_at)
        validated_article_rows += int(is_article)
        if item is not None:
            items.append(item)
    if not validated_article_rows:
        raise InvalidSourcePage("no canonical article rows found")
    return items
