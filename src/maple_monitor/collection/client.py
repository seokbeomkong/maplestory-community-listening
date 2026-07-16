from __future__ import annotations

from contextlib import nullcontext
from typing import Final

import httpx

from maple_monitor.sources import source_for_board

MAX_LIST_RESPONSE_BYTES: Final = 512_000
MAX_LIST_PAGE: Final = 100_000
USER_AGENT: Final = "maple-inven-monitor/0.1 (bounded public metadata collector)"
REQUEST_TIMEOUT: Final = httpx.Timeout(10.0, connect=5.0, write=5.0, pool=5.0)

_REQUEST_HEADERS: Final = {
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Encoding": "identity",
    "User-Agent": USER_AGENT,
}


class ListPageClientError(RuntimeError):
    """Base class for list fetch failures safe to report without upstream details."""


class InvalidListPageTarget(ListPageClientError, ValueError):
    """Raised before I/O when a requested board or page is outside the allow list."""


class ListPageTransportError(ListPageClientError):
    """Raised when the allow-listed request cannot be completed."""


class ListPageResponseError(ListPageClientError):
    """Raised when the allow-listed endpoint returns an unusable response."""


class ListPageRedirectError(ListPageResponseError):
    """Raised when the endpoint attempts to redirect the bounded request."""


class ListPageTooLargeError(ListPageResponseError):
    """Raised when declared or streamed response bytes exceed the hard cap."""


def _validate_board_id(board_id: int) -> None:
    try:
        source_for_board(board_id)
    except TypeError:
        raise InvalidListPageTarget("board must be an allow-listed board identifier") from None
    except ValueError:
        raise InvalidListPageTarget("unsupported board") from None


def _validate_page(page: int) -> None:
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= MAX_LIST_PAGE:
        raise InvalidListPageTarget("page must be between 1 and 100000")


def _validate_content_length(value: str | None) -> None:
    if value is None:
        return
    try:
        declared_size = int(value)
    except ValueError:
        raise ListPageResponseError("list page response metadata is invalid") from None
    if declared_size < 0:
        raise ListPageResponseError("list page response metadata is invalid")
    if declared_size > MAX_LIST_RESPONSE_BYTES:
        raise ListPageTooLargeError("list page response exceeds the size limit")


def _read_bounded(response: httpx.Response) -> bytes:
    content_encoding = response.headers.get("content-encoding", "").strip().casefold()
    if content_encoding not in ("", "identity"):
        raise ListPageResponseError("list page response encoding is unsupported")
    _validate_content_length(response.headers.get("content-length"))
    body = bytearray()
    for chunk in response.iter_bytes():
        if len(chunk) > MAX_LIST_RESPONSE_BYTES - len(body):
            raise ListPageTooLargeError("list page response exceeds the size limit")
        body.extend(chunk)
    return bytes(body)


def fetch_list_page(
    board_id: int,
    page: int = 1,
    *,
    client: httpx.Client | None = None,
) -> bytes:
    """Fetch one public board list with a fixed target and bounded response body.

    Redirects are deliberately refused. Public exceptions contain only stable local
    diagnostics; upstream URLs, response bodies, and transport messages are never copied.
    """

    _validate_board_id(board_id)
    _validate_page(page)
    target = httpx.URL(f"https://www.inven.co.kr/board/maple/{board_id}", params={"p": page})
    owned_client = httpx.Client(follow_redirects=False, trust_env=False) if client is None else None
    client_context = owned_client if owned_client is not None else nullcontext(client)

    try:
        with client_context as active_client:
            assert active_client is not None
            with active_client.stream(
                "GET",
                target,
                headers=_REQUEST_HEADERS,
                timeout=REQUEST_TIMEOUT,
                follow_redirects=False,
            ) as response:
                if response.url != target:
                    raise ListPageResponseError("list page response target is invalid")
                if response.is_redirect:
                    raise ListPageRedirectError("list page request was redirected")
                if response.status_code != httpx.codes.OK or "content-range" in response.headers:
                    raise ListPageResponseError("list page response is incomplete")
                return _read_bounded(response)
    except httpx.HTTPError:
        raise ListPageTransportError("list page request failed") from None
