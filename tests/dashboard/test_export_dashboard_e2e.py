from __future__ import annotations

from pathlib import Path


def test_operations_guide_documents_export_dashboard_launch() -> None:
    guide = Path("docs/operations/vps-production.md").read_text(encoding="utf-8")

    assert "MAPLE_EXPORT_PATH" in guide
    assert "maple_monitor/dashboard/export_app.py" in guide


def test_dashboard_theme_is_native_light_editorial() -> None:
    theme = Path(".streamlit/config.toml").read_text(encoding="utf-8")

    assert 'base = "light"' in theme
    assert 'backgroundColor = "#F7F6F2"' in theme
    assert "<style>" not in theme
