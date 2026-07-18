from __future__ import annotations

import pandas as pd

from maple_monitor.dashboard.export_charts import job_constellation


def test_job_constellation_encodes_volume_and_response_without_composite_score() -> None:
    comparison = pd.DataFrame(
        [
            {
                "job": "히어로",
                "analysis_unit": "hero",
                "sample_size": 5,
                "comments_per_post": 2.0,
                "total_views": 1_000,
                "recommendations_per_post": 0.8,
                "total_comments": 10,
                "total_recommendations": 4,
                "views_per_post": 200.0,
                "effective_hours": 168,
                "analysis_period": "2026.07.10–2026.07.17",
                "fallback_reason": None,
            }
        ]
    )

    spec = job_constellation(comparison).to_dict()
    encoding = spec["encoding"]

    assert encoding["x"]["field"] == "sample_size"
    assert encoding["y"]["field"] == "comments_per_post"
    assert encoding["size"]["field"] == "total_views"
    assert encoding["color"]["field"] == "recommendations_per_post"
    tooltip_fields = {item["field"] for item in encoding["tooltip"]}
    assert {
        "total_comments",
        "comments_per_post",
        "total_recommendations",
        "recommendations_per_post",
        "total_views",
        "views_per_post",
    } <= tooltip_fields
    tooltip_formats = {item["field"]: item.get("format") for item in encoding["tooltip"]}
    assert tooltip_formats["comments_per_post"] == ".1f"
    assert tooltip_formats["recommendations_per_post"] == ".1f"
    assert tooltip_formats["views_per_post"] == ".1f"
    assert "analysis_period" in tooltip_fields
    assert "engagement_score" not in str(spec)
