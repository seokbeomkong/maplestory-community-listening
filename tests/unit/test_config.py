from pathlib import Path

import pytest

from maple_monitor.config import load_settings


def test_defaults_are_operator_visible_and_weights_normalize(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text(
        """
collection:
  interval_hours: 6
  slot_minute_kst: 20
  request_min_delay_seconds: 1.5
  request_max_delay_seconds: 3.0
  concurrency: 1
  max_retries: 3
ranking:
  window_days: 90
  top_n: 50
rising:
  windows_hours: [24, 168, 720]
  recommendation_weight: 50
  comment_weight: 35
  view_weight: 15
  acceleration_weight: 0.30
  boundary_tolerance_hours: 3
  category_top_k: 5
  category_min_posts: 3
  category_top_mean_weight: 0.70
analysis:
  local_batch_size: 50
  codex_max_items_per_session: 40
  codex_estimated_input_token_budget: 20000
  codex_prompt_version: opinion-v1
  codex_model_version: codex-manual-v1
security:
  quarantine_threshold: 70
retention:
  raw_html_days: 30
  full_text_days: 90
resources:
  disk_warn_percent: 70
  disk_pause_percent: 85
""".strip(),
        encoding="utf-8",
    )

    loaded = load_settings(path)

    assert loaded.settings.collection.interval_hours == 6
    assert loaded.settings.ranking.top_n == 50
    assert loaded.settings.rising.normalized_weights().model_dump() == {
        "recommendation": 0.5,
        "comment": 0.35,
        "view": 0.15,
    }
    assert len(loaded.config_version) == 64


def test_interval_must_divide_day(tmp_path: Path) -> None:
    source = Path("config/settings.yaml").read_text(encoding="utf-8")
    path = tmp_path / "bad.yaml"
    path.write_text(source.replace("interval_hours: 6", "interval_hours: 5"), encoding="utf-8")

    with pytest.raises(ValueError, match="divide 24"):
        load_settings(path)


def test_invalid_reload_does_not_replace_last_valid_configuration(tmp_path: Path) -> None:
    from maple_monitor.config import SettingsStore

    path = tmp_path / "settings.yaml"
    path.write_text(Path("config/settings.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    store = SettingsStore(path)
    first = store.current
    path.write_text("collection: {interval_hours: 0}", encoding="utf-8")

    assert store.reload() is False
    assert store.current.config_version == first.config_version
    assert store.last_error is not None
