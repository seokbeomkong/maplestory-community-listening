from __future__ import annotations

import altair as alt
import pandas as pd


def job_constellation(comparison: pd.DataFrame) -> alt.Chart:
    """Map job-board volume and response as separate, inspectable signals."""

    frame = comparison.copy()
    frame["기간"] = frame["effective_hours"].map(lambda value: f"{int(value) // 24}일")
    return (
        alt.Chart(frame)
        .mark_circle(opacity=0.86, stroke="#E8D99B", strokeWidth=1.1)
        .encode(
            x=alt.X("sample_size:Q", title="수집 게시물", scale=alt.Scale(zero=True)),
            y=alt.Y(
                "comments_per_post:Q",
                title="게시물당 댓글",
                scale=alt.Scale(zero=True),
            ),
            size=alt.Size(
                "total_views:Q",
                title="총 조회",
                scale=alt.Scale(range=[90, 1_400]),
            ),
            color=alt.Color(
                "recommendations_per_post:Q",
                title="게시물당 추천",
                scale=alt.Scale(range=["#6670A6", "#E0C878"]),
            ),
            tooltip=[
                alt.Tooltip("job:N", title="직업"),
                alt.Tooltip("sample_size:Q", title="게시물", format=",d"),
                alt.Tooltip("total_comments:Q", title="총 댓글", format=",d"),
                alt.Tooltip("comments_per_post:Q", title="게시물당 댓글", format=".2f"),
                alt.Tooltip("total_recommendations:Q", title="총 추천", format=",d"),
                alt.Tooltip(
                    "recommendations_per_post:Q", title="게시물당 추천", format=".2f"
                ),
                alt.Tooltip("total_views:Q", title="총 조회", format=",d"),
                alt.Tooltip("views_per_post:Q", title="게시물당 조회", format=".2f"),
                alt.Tooltip("기간:N", title="분석 기간"),
            ],
        )
        .properties(height=480)
        .interactive()
    )
