from __future__ import annotations

from typing import Any

import pandas as pd

from maple_monitor.dashboard.export_analysis import (
    collection_health,
    engagement_totals,
    job_comparison,
)
from maple_monitor.dashboard.export_data import ExportBundle


def _json_value(value: object) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()  # type: ignore[no-any-return, union-attr]
    return value


def _json_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {column: _json_value(value) for column, value in record.items()}
        for record in frame.to_dict(orient="records")
    ]


def portfolio_snapshot(bundle: ExportBundle) -> dict[str, object]:
    """Build the canonical serializable portfolio data contract."""

    health = collection_health(bundle)
    latest = bundle.posts["observed_at_slot_kst"].max()
    return {
        "source": {
            "path": str(bundle.source_path),
            "latest_observation": pd.Timestamp(latest).isoformat(),
            "checksums_verified": sum(bundle.checksums.values()),
            "checksums_total": len(bundle.checksums),
        },
        "totals": engagement_totals(bundle.posts),
        "collection": {
            "total_runs": health.total_runs,
            "succeeded_runs": health.succeeded_runs,
            "failed_runs": health.failed_runs,
            "partial_runs": health.partial_runs,
            "success_rate": health.success_rate,
        },
        "jobs": _json_records(job_comparison(bundle.posts)),
        "analysis_status": {
            "source_metrics": "available",
            "label_schema": "designed",
            "gold_dataset": "requires_text_labels",
            "baseline_model": "designed",
            "slm_experiment": "requires_text_labels",
        },
    }
