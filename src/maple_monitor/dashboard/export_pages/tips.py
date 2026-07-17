from __future__ import annotations

import streamlit as st

from maple_monitor.dashboard.export_analysis import rank_posts, select_window
from maple_monitor.dashboard.export_context import optional_analysis_artifact, require_export_bundle
from maple_monitor.dashboard.export_semantics import render_semantic_summary, semantic_summary
from maple_monitor.dashboard.export_pages.shared import (
    render_evidence_table,
    render_source_caption,
)


bundle = require_export_bundle()
selection = select_window(bundle.posts, "tips", hours=720)
st.subheader("30일 인기 정보")
render_source_caption(bundle, selection)
metric_label = st.segmented_control("정렬 기준", ["추천", "조회", "댓글"], default="추천")
metric = {"댓글": "comments", "추천": "recommendations", "조회": "views"}[metric_label]
render_evidence_table(rank_posts(selection.rows, metric, limit=20), metric)
st.caption("인기 지표이며 정보의 정확성이나 최신성을 보증하지 않습니다.")

artifact = optional_analysis_artifact(bundle)
if artifact is not None and (summary := semantic_summary(artifact, "tips")) is not None:
    st.subheader("90일 상위 반응 표본 · 정보 주제와 댓글 반응")
    render_semantic_summary(summary, scope_label="팁과 노하우 게시물만")
