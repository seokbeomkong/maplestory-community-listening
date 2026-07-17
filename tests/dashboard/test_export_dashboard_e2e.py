from __future__ import annotations

from pathlib import Path


def test_operations_guide_documents_export_dashboard_launch() -> None:
    guide = Path("docs/operations/vps-production.md").read_text(encoding="utf-8")

    assert "MAPLE_EXPORT_PATH" in guide
    assert "maple_monitor/dashboard/export_app.py" in guide


def test_dashboard_theme_uses_lethe_midnight_palette() -> None:
    theme = Path(".streamlit/config.toml").read_text(encoding="utf-8")

    assert 'base = "dark"' in theme
    assert 'backgroundColor = "#090B19"' in theme
    assert 'primaryColor = "#D8C47C"' in theme


def test_official_asset_manifest_references_only_nexon_sources() -> None:
    manifest = Path("docs/assets/official-sources.md").read_text(encoding="utf-8")

    assert "서약의 지배자, 레테" in manifest
    assert "maplestory.nexon.com" in manifest
    assert "lwi.nexon.com" in manifest
    assert "unsplash" not in manifest.lower()
