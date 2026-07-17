from __future__ import annotations

import json
from pathlib import Path

from maple_monitor.dashboard.export_data import load_export_archive
from maple_monitor.dashboard.export_presentation import portfolio_snapshot


def test_portfolio_snapshot_is_json_serializable(export_zip: Path) -> None:
    bundle = load_export_archive(export_zip)

    snapshot = portfolio_snapshot(bundle)

    assert snapshot["totals"] == {
        "posts": 4,
        "comments": 25,
        "recommendations": 30,
        "views": 3500,
    }
    assert snapshot["source"]["latest_observation"].endswith("+00:00")
    assert snapshot["source"]["checksums_verified"] == 4
    assert snapshot["source"]["archive"] == export_zip.name
    assert str(export_zip.parent) not in str(snapshot)
    assert snapshot["collection"]["failed_runs"] == 1
    assert snapshot["jobs"][0]["job"] == "히어로"
    json.dumps(snapshot, ensure_ascii=False)
