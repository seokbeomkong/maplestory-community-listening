from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


_PAGES = Path(__file__).parents[2] / "src" / "maple_monitor" / "dashboard" / "export_pages"


@pytest.mark.parametrize(
    ("page_name", "required"),
    [
        ("jobs.py", "7일 표본 부족"),
        ("free.py", "24시간 주요 게시물"),
        ("qna.py", "댓글 0건 질문"),
        ("tips.py", "30일 인기 정보"),
        ("operations.py", "수집 실패"),
    ],
)
def test_board_pages_use_source_appropriate_language(
    monkeypatch,
    export_zip: Path,
    page_name: str,
    required: str,
) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(export_zip))

    page = AppTest.from_file(_PAGES / page_name).run(timeout=10)

    assert not page.exception
    values = [
        item.value
        for collection in (
            page.header,
            page.subheader,
            page.caption,
            page.info,
            page.warning,
            page.error,
        )
        for item in collection
    ]
    assert any(required in value for value in values)


def test_qna_page_does_not_claim_zero_comments_are_unresolved(
    monkeypatch, export_zip: Path
) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(export_zip))

    page = AppTest.from_file(_PAGES / "qna.py").run(timeout=10)

    assert "미해결 확정" not in str(page)
