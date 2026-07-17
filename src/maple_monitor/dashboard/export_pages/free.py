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
selection = select_window(bundle.posts, "free", hours=24)
st.subheader("24시간 주요 게시물")
render_source_caption(bundle, selection)
metric_label = st.segmented_control("정렬 기준", ["댓글", "추천", "조회"], default="댓글")
metric = {"댓글": "comments", "추천": "recommendations", "조회": "views"}[metric_label]
render_evidence_table(rank_posts(selection.rows, metric, limit=20), metric)

st.subheader("90일 상위 반응 표본 · 이슈와 반응")
artifact = optional_analysis_artifact(bundle)
if artifact is not None and (summary := semantic_summary(artifact, "free")) is not None:
    render_semantic_summary(summary, scope_label="자유게시판 게시물만")
