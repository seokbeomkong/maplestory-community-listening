from __future__ import annotations

import streamlit as st

from maple_monitor.dashboard.export_analysis import rank_posts, select_window
from maple_monitor.dashboard.export_context import require_export_bundle
from maple_monitor.dashboard.export_pages.shared import render_evidence_table, render_source_caption


bundle = require_export_bundle()
selection = select_window(bundle.posts, "tips", hours=720)
st.subheader("30일 인기 정보")
render_source_caption(bundle, selection)
metric_label = st.segmented_control("정렬 기준", ["추천", "조회", "댓글"], default="추천")
metric = {"댓글": "comments", "추천": "recommendations", "조회": "views"}[metric_label]
render_evidence_table(rank_posts(selection.rows, metric, limit=20), metric)
st.caption("인기 지표이며 정보의 정확성이나 최신성을 보증하지 않습니다.")
