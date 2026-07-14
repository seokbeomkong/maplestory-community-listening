from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy.exc import OperationalError
from streamlit.testing.v1 import AppTest


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "rank": 1,
                "title": "테스트 게시물",
                "metric_value": 42,
                "published_at": "2026-07-15T05:00:00+09:00",
                "source_url": "https://example.invalid/posts/1",
                "as_of_slot_kst": "2026-07-15T06:00:00+09:00",
                "config_version": "c" * 64,
            }
        ]
    )


def _render_app() -> None:
    from maple_monitor.dashboard.pages.cumulative import render

    render(object())


def test_cumulative_page_renders_source_backed_rankings(monkeypatch) -> None:
    from maple_monitor.dashboard.pages import cumulative

    monkeypatch.setattr(cumulative, "load_cumulative_top", lambda *_args: _frame())

    page = AppTest.from_function(_render_app).run()

    assert not page.exception
    assert any("누적 상위 50" in header.value for header in page.header)
    assert "최근 90일" in " ".join(caption.value for caption in page.caption)
    assert "급상승 순위와 별도" in " ".join(caption.value for caption in page.caption)
    assert "기준 시각" in " ".join(caption.value for caption in page.caption)
    assert "c" * 12 in " ".join(caption.value for caption in page.caption)
    assert "급상승 점수" not in str(page)
    assert len(page.dataframe) == 1
    assert page.dataframe[0].value["rank"].tolist() == [1]


def test_cumulative_page_exercises_all_metric_choices(monkeypatch) -> None:
    from maple_monitor.dashboard.pages import cumulative

    calls: list[tuple[str, str]] = []

    def load(_engine: object, analysis_unit: str, metric: str) -> pd.DataFrame:
        calls.append((analysis_unit, metric))
        return _frame()

    monkeypatch.setattr(cumulative, "load_cumulative_top", load)
    page = AppTest.from_function(_render_app).run()
    assert calls == [("hero", "recommendations")]
    assert page.selectbox[0].value == "hero"
    assert page.selectbox[0].options == ["히어로"]
    assert page.selectbox[1].value == "recommendations"
    assert page.selectbox[1].options == ["추천", "댓글", "조회"]

    page.selectbox[1].select("comments").run()
    page.selectbox[1].select("views").run()

    assert calls == [
        ("hero", "recommendations"),
        ("hero", "comments"),
        ("hero", "views"),
    ]


def test_cumulative_page_has_explicit_empty_state(monkeypatch) -> None:
    from maple_monitor.dashboard.pages import cumulative

    monkeypatch.setattr(
        cumulative,
        "load_cumulative_top",
        lambda *_args: _frame().iloc[0:0],
    )

    page = AppTest.from_function(_render_app).run()

    assert not page.exception
    assert len(page.dataframe) == 0
    assert any("데이터가 없습니다" in item.value for item in page.info)


def test_cumulative_page_hides_connection_errors_and_secrets(monkeypatch) -> None:
    from maple_monitor.dashboard.pages import cumulative

    secret = "raw-database-secret"

    def fail(*_args: object) -> pd.DataFrame:
        raise OperationalError("SELECT secret", {}, RuntimeError(secret))

    monkeypatch.setattr(cumulative, "load_cumulative_top", fail)

    page = AppTest.from_function(_render_app).run()

    assert not page.exception
    assert any("데이터베이스 설정" in item.value for item in page.error)
    assert secret not in str(page)
    assert len(page.dataframe) == 0


def test_dashboard_entrypoint_shows_safe_missing_configuration(
    monkeypatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app_path = Path(__file__).parents[2] / "src" / "maple_monitor" / "dashboard" / "app.py"

    page = AppTest.from_file(app_path).run()

    assert not page.exception
    assert any("데이터베이스 설정" in item.value for item in page.error)
