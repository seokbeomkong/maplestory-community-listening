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


def test_portfolio_publishing_guide_keeps_interactivity_in_canonical_app() -> None:
    guide = Path("docs/portfolio/publishing.md").read_text(encoding="utf-8")

    assert "Streamlit" in guide
    assert "portfolio_snapshot" in guide
    assert "PPT/PDF" in guide
    assert "QR" in guide


def test_theme_preserves_streamlit_material_symbol_fonts() -> None:
    theme_source = Path("src/maple_monitor/dashboard/export_theme.py").read_text(encoding="utf-8")

    assert '[class*="st-"]' not in theme_source
    assert "min-height: 410px" in theme_source
    assert "background-position: 52% 42%" in theme_source


def test_local_dashboard_guide_uses_export_directory_for_automatic_refresh() -> None:
    guide = Path("docs/portfolio/local-data-refresh.md").read_text(encoding="utf-8")

    assert '$env:MAPLE_EXPORT_PATH = "C:\\Users\\tjrqj\\Documents\\Maplestory\\exports"' in guide
    assert "최신 ZIP" in guide
    assert "Windows 작업 스케줄러" in guide


def test_app_watches_export_directory_for_completed_releases() -> None:
    app_source = Path("src/maple_monitor/dashboard/export_app.py").read_text(encoding="utf-8")

    assert "@st.fragment(run_every=30)" in app_source
    assert "export_signature" in app_source
    assert "st.rerun()" in app_source
    assert "MAPLE_ANALYSIS_ROOT" in app_source
    assert "manifest.json" in app_source


def test_one_command_local_dashboard_launcher_uses_export_directory() -> None:
    launcher = Path("scripts/start-local-dashboard.ps1").read_text(encoding="utf-8")

    assert "MAPLE_EXPORT_PATH" in launcher
    assert "exports" in launcher
    assert "-m streamlit" in launcher
    assert "export_app.py" in launcher
    assert "analyze-export" in launcher
    assert "MAPLE_ANALYSIS_ROOT" in launcher
    assert launcher.index("analyze-export") < launcher.index("-m streamlit")
    assert "Start-Job" in launcher
