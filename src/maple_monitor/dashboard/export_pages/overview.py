from __future__ import annotations

import streamlit as st

from maple_monitor.dashboard.export_analysis import (
    collection_health,
    job_comparison,
    rank_posts,
    select_window,
    semantic_availability,
)
from maple_monitor.dashboard.export_context import require_export_bundle
from maple_monitor.dashboard.export_pages.shared import (
    render_evidence_table,
    render_semantic_state,
    render_source_caption,
)


bundle = require_export_bundle()
health = collection_health(bundle)
availability = semantic_availability(bundle)

render_source_caption(bundle)
with st.container(horizontal=True):
    st.metric("수집 게시물", f"{len(bundle.posts):,}건", border=True)
    st.metric("분석 단위", f"{bundle.posts['analysis_unit'].nunique():,}개", border=True)
    st.metric("수집 성공률", f"{health.success_rate:.0%}", border=True)
    st.metric("실패 실행", f"{health.failed_runs:,}건", border=True)

st.subheader("직업 게시판 현황")
comparison = job_comparison(bundle.posts)
if comparison.empty:
    st.caption("비교할 직업 게시물이 없습니다.")
else:
    chart = comparison.head(12).rename(
        columns={"job": "직업", "comments_per_post": "게시물당 댓글"}
    )
    st.bar_chart(chart, x="직업", y="게시물당 댓글", horizontal=True)
    st.caption("게시판 규모 차이를 줄이기 위해 게시물당 댓글을 함께 봅니다.")

st.subheader("자유게시판 주요 게시물")
free_window = select_window(bundle.posts, "free", hours=24)
render_source_caption(bundle, free_window)
render_evidence_table(rank_posts(free_window.rows, "comments", limit=8), "comments")

st.subheader("반응 분석 상태")
render_semantic_state(availability)
