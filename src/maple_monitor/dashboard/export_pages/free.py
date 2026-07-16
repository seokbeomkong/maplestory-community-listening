from __future__ import annotations

import streamlit as st

from maple_monitor.dashboard.export_analysis import rank_posts, select_window, semantic_availability
from maple_monitor.dashboard.export_context import require_export_bundle
from maple_monitor.dashboard.export_pages.shared import (
    render_evidence_table,
    render_semantic_state,
    render_source_caption,
)


bundle = require_export_bundle()
selection = select_window(bundle.posts, "free", hours=24)
st.subheader("24시간 주요 게시물")
render_source_caption(bundle, selection)
metric_label = st.segmented_control("정렬 기준", ["댓글", "추천", "조회"], default="댓글")
metric = {"댓글": "comments", "추천": "recommendations", "조회": "views"}[metric_label]
render_evidence_table(rank_posts(selection.rows, metric, limit=20), metric)

st.subheader("이슈와 반응")
render_semantic_state(semantic_availability(bundle))
