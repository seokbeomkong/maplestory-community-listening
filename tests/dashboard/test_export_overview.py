from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


_APP = Path(__file__).parents[2] / "src" / "maple_monitor" / "dashboard" / "export_app.py"


def test_export_app_renders_portfolio_story(monkeypatch, export_zip: Path) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(export_zip))

    page = AppTest.from_file(_APP).run(timeout=10)

    assert not page.exception
    assert any("프로젝트" in item.value for item in page.title)
    assert any("실시간 유저 반응 관측" in item.value for item in page.header)
    assert any("최신 수집" in item.value for item in page.caption)
    assert any("직업 별자리" in item.value for item in page.subheader)
    assert any("분석 워크플로우" in item.value for item in page.subheader)
    assert any("© NEXON Korea" in item.value for item in page.caption)


def test_export_app_hides_missing_path_details(monkeypatch) -> None:
    monkeypatch.delenv("MAPLE_EXPORT_PATH", raising=False)

    page = AppTest.from_file(_APP).run()

    assert not page.exception
    assert any("MAPLE_EXPORT_PATH" in item.value for item in page.error)


def test_experiment_page_explains_nlp_and_multimodal_modeling(
    monkeypatch, export_zip: Path, analysis_root: Path
) -> None:
    monkeypatch.setenv("MAPLE_EXPORT_PATH", str(export_zip))
    monkeypatch.setenv("MAPLE_ANALYSIS_ROOT", str(analysis_root))
    experiment = _APP.parent / "export_pages" / "experiment.py"

    page = AppTest.from_file(experiment).run(timeout=10)

    assert not page.exception
    assert any("자연어 처리와 언어모델을 어디에 쓰는가" in item.value for item in page.subheader)
    assert any("텍스트 멀티모달 모델 구조" in item.value for item in page.subheader)
    assert any("새 데이터가 들어왔을 때" in item.value for item in page.subheader)
    assert any("모델이 하지 않는 일" in item.value for item in page.subheader)
    assert "분류 기준과 해석 방법" in str(page)
    assert any("주제**는 제목과 본문" in item.value for item in page.markdown)
    assert any("2026.07.10–2026.07.16 게시물" in item.value for item in page.caption)
    rendered = str(page)
    assert "MODEL DEVELOPMENT BLUEPRINT" not in rendered
    assert "NOT YET EXECUTED" not in rendered
    assert "채용 직무와 연결" not in rendered
    assert "결과 상태" not in rendered
