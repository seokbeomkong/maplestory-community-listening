from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


_APP = Path(__file__).parents[2] / "src" / "maple_monitor" / "dashboard" / "export_app.py"


def test_export_app_renders_portfolio_story(monkeypatch, export_zip: Path) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(export_zip))

    page = AppTest.from_file(_APP).run(timeout=10)

    assert not page.exception
    assert any("프로젝트" in item.value for item in page.title)
    assert any("커뮤니티의 목소리를 검증 가능한 데이터로" in item.value for item in page.header)
    assert any("최신 수집" in item.value for item in page.caption)
    assert any("직업 별자리" in item.value for item in page.subheader)
    assert any("데이터 한계" in item.value for item in page.subheader)


def test_export_app_hides_missing_path_details(monkeypatch) -> None:
    monkeypatch.delenv("MAPLE_EXPORT_PATH", raising=False)

    page = AppTest.from_file(_APP).run()

    assert not page.exception
    assert any("MAPLE_EXPORT_PATH" in item.value for item in page.error)
