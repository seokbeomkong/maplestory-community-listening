from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest


class _ChunkStream(httpx.SyncByteStream):
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self._chunks = chunks

    def __iter__(self) -> Iterator[bytes]:
        return iter(self._chunks)


class _NeverReadStream(httpx.SyncByteStream):
    def __iter__(self) -> Iterator[bytes]:
        raise AssertionError("an encoded response must be rejected before decompression")


def test_fetches_only_the_supported_https_list_target_with_safe_headers() -> None:
    from maple_monitor.collection.client import USER_AGENT, fetch_list_page

    captured: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, content=b"<html>bounded</html>", request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        body = fetch_list_page(2294, client=client)

    assert body == b"<html>bounded</html>"
    assert len(captured) == 1
    request = captured[0]
    assert request.url == httpx.URL(
        "https://www.inven.co.kr/board/maple/2294?category=%ED%9E%88%EC%96%B4%EB%A1%9C"
    )
    assert request.headers["user-agent"] == USER_AGENT
    assert "Mozilla" not in USER_AGENT
    assert "text/html" in request.headers["accept"]
    assert request.headers["accept-encoding"] == "identity"
    assert request.extensions["timeout"] == {
        "connect": 5.0,
        "read": 10.0,
        "write": 5.0,
        "pool": 5.0,
    }


def test_rejects_an_unsupported_board_before_transport_use() -> None:
    from maple_monitor.collection.client import InvalidListPageTarget, fetch_list_page

    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b"unexpected", request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(InvalidListPageTarget, match="unsupported board"):
            fetch_list_page(2295, client=client)

    assert calls == 0


def test_refuses_redirects_without_requesting_the_redirect_target() -> None:
    from maple_monitor.collection.client import ListPageRedirectError, fetch_list_page

    requested: list[str] = []
    secret_target = "http://127.0.0.1/private?token=do-not-leak"

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": secret_target},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ListPageRedirectError) as caught:
            fetch_list_page(2294, client=client)

    assert requested == [
        "https://www.inven.co.kr/board/maple/2294?category=%ED%9E%88%EC%96%B4%EB%A1%9C"
    ]
    assert secret_target not in str(caught.value)
    assert "token" not in str(caught.value)


def test_redacts_transport_failure_details_and_exception_chaining() -> None:
    from maple_monitor.collection.client import ListPageTransportError, fetch_list_page

    leaked_detail = "https://user:secret@outside.example/?token=do-not-leak"

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(leaked_detail, request=request)

    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(ListPageTransportError) as caught:
            fetch_list_page(2294, client=client)

    assert leaked_detail not in str(caught.value)
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_redacts_non_success_response_body() -> None:
    from maple_monitor.collection.client import ListPageResponseError, fetch_list_page

    leaked_body = "upstream secret token=do-not-leak"

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text=leaked_body, request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ListPageResponseError) as caught:
            fetch_list_page(2294, client=client)

    assert leaked_body not in str(caught.value)
    assert "503" not in str(caught.value)


def test_rejects_declared_response_above_the_byte_cap() -> None:
    from maple_monitor.collection.client import (
        MAX_LIST_RESPONSE_BYTES,
        ListPageTooLargeError,
        fetch_list_page,
    )

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-length": str(MAX_LIST_RESPONSE_BYTES + 1)},
            stream=_ChunkStream((b"not read",)),
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ListPageTooLargeError, match="size limit"):
            fetch_list_page(2294, client=client)


def test_stops_streaming_when_the_decompressed_byte_cap_is_crossed() -> None:
    from maple_monitor.collection.client import (
        MAX_LIST_RESPONSE_BYTES,
        ListPageTooLargeError,
        fetch_list_page,
    )

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=_ChunkStream(
                (
                    b"a" * MAX_LIST_RESPONSE_BYTES,
                    b"b",
                    b"must never be read",
                )
            ),
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ListPageTooLargeError, match="size limit"):
            fetch_list_page(2294, client=client)


def test_rejects_encoded_response_before_decompression() -> None:
    from maple_monitor.collection.client import ListPageResponseError, fetch_list_page

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip"},
            stream=_NeverReadStream(),
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ListPageResponseError, match="encoding"):
            fetch_list_page(2294, client=client)
