from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


_APP = Path(__file__).parents[2] / "src" / "maple_monitor" / "dashboard" / "export_app.py"


def test_export_app_renders_factual_overview(monkeypatch, export_zip: Path) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(export_zip))

    page = AppTest.from_file(_APP).run(timeout=10)

    assert not page.exception
    assert any("종합 현황" in item.value for item in page.title)
    assert any("감성 분석 데이터 없음" in item.value for item in page.info)
    assert any("최신 수집" in item.value for item in page.caption)
    assert any("주요 게시물" in item.value for item in page.subheader)


def test_export_app_hides_missing_path_details(monkeypatch) -> None:
    monkeypatch.delenv("MAPLE_EXPORT_PATH", raising=False)

    page = AppTest.from_file(_APP).run()

    assert not page.exception
    assert any("MAPLE_EXPORT_PATH" in item.value for item in page.error)
