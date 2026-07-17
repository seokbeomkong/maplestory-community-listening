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
    assert "engagement_score" not in str(spec)
