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


def test_job_sort_control_recovers_when_selection_is_cleared(monkeypatch, export_zip: Path) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(export_zip))

    page = AppTest.from_file(_PAGES / "jobs.py").run(timeout=10)

    page.segmented_control[0].set_value(None)
    page.run(timeout=10)

    assert not page.exception
    assert any("댓글 8 순" in item.value for item in page.subheader)


@pytest.mark.parametrize("page_name", ["jobs.py", "free.py", "qna.py", "tips.py"])
def test_portfolio_pages_do_not_show_assistant_facing_missing_data_copy(
    monkeypatch, export_zip: Path, page_name: str
) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(export_zip))

    page = AppTest.from_file(_PAGES / page_name).run(timeout=10)

    assert not page.exception
    assert "감성 분석 데이터 없음" not in str(page)


def test_overview_discloses_job_comparison_window(monkeypatch, export_zip: Path) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(export_zip))

    page = AppTest.from_file(_PAGES / "overview.py").run(timeout=10)

    assert not page.exception
    assert any("7일 표본 부족으로 30일 확장" in item.value for item in page.caption)
    assert any("2026.07.10–2026.07.16 게시물" in item.value for item in page.caption)


def test_empty_export_renders_an_explicit_empty_state(monkeypatch, empty_export_zip: Path) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(empty_export_zip))

    page = AppTest.from_file(_PAGES / "overview.py").run(timeout=10)

    assert not page.exception
    assert any("게시물 데이터가 없습니다" in item.value for item in page.warning)


def test_job_page_shows_four_totals_and_counted_sort_options(monkeypatch, export_zip: Path) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(export_zip))

    page = AppTest.from_file(_PAGES / "jobs.py").run(timeout=10)

    assert not page.exception
    assert {metric.label for metric in page.metric} >= {"게시물", "댓글", "추천", "조회"}
    rendered = str(page)
    assert "댓글 8" in rendered
    assert "추천 3" in rendered
    assert "조회 500" in rendered


def test_job_semantics_declares_exact_scope_and_four_classification_views(
    monkeypatch, export_zip: Path, analysis_root: Path
) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(export_zip))
    monkeypatch.setenv("MAPLE_ANALYSIS_ROOT", str(analysis_root))

    page = AppTest.from_file(_PAGES / "jobs.py").run(timeout=10)

    assert not page.exception
    assert any("히어로 직업 카테고리 게시물만" in item.value for item in page.caption), [
        item.value for item in page.caption
    ]
    markdown_values = [item.value for item in page.markdown]
    assert any("주요 주제" in value for value in markdown_values)
    assert any("작성 의도" in value for value in markdown_values)
    assert any("작성 글 감성" in value for value in markdown_values)
    assert any("댓글 반응" in value for value in markdown_values)
    assert any("주제**는 제목과 본문" in value for value in markdown_values), markdown_values
