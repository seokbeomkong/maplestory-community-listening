from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Final

import httpx


COMMENT_URL: Final = "https://www.inven.co.kr/common/board/comment.json.php"
MAX_ARTICLE_BYTES: Final = 5_000_000
MAX_COMMENT_BYTES: Final = 2_000_000


class DetailClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class RawDetail:
    article: bytes
    comments: bytes


class DetailClient:
    def __init__(self, minimum_delay: float = 1.5, maximum_delay: float = 3.0) -> None:
        self._minimum_delay = minimum_delay
        self._maximum_delay = maximum_delay
        self._client = httpx.Client(
            headers={"User-Agent": "MapleCommunityResearch/1.0 (public portfolio analysis)"},
            follow_redirects=True,
            timeout=20,
        )
        self._last_request_at: float | None = None

    def __enter__(self) -> DetailClient:
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    def _wait(self) -> None:
        if self._last_request_at is not None:
            target = random.uniform(self._minimum_delay, self._maximum_delay)
            remaining = target - (time.monotonic() - self._last_request_at)
            if remaining > 0:
                time.sleep(remaining)

    def _request(self, method: str, url: str, **kwargs: object) -> bytes:
        self._wait()
        response = self._client.request(method, url, **kwargs)
        self._last_request_at = time.monotonic()
        if response.status_code != httpx.codes.OK:
            raise DetailClientError("detail source did not return HTTP 200")
        return response.content

    def fetch(self, board_id: int, post_id: int) -> RawDetail:
        article_url = f"https://www.inven.co.kr/board/maple/{int(board_id)}/{int(post_id)}"
        article = self._request("GET", article_url)
        if len(article) > MAX_ARTICLE_BYTES:
            raise DetailClientError("article response exceeds the byte limit")
        comments = self._request(
            "POST",
            COMMENT_URL,
            headers={"Referer": article_url, "Origin": "https://www.inven.co.kr"},
            data={
                "comeidx": str(int(board_id)),
                "articlecode": str(int(post_id)),
                "sortorder": "date",
                "act": "list",
                "out": "json",
                "replynick": "",
                "replyidx": "0",
            },
        )
        if len(comments) > MAX_COMMENT_BYTES:
            raise DetailClientError("comment response exceeds the byte limit")
        return RawDetail(article=article, comments=comments)
