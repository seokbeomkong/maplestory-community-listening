from __future__ import annotations

import streamlit as st

from maple_monitor.dashboard.export_analysis import (
    engagement_totals,
    rank_posts,
    select_window,
)
from maple_monitor.dashboard.export_context import (
    optional_analysis_artifact,
    require_export_bundle,
)
from maple_monitor.dashboard.export_semantics import (
    render_semantic_summary,
    semantic_summary,
)
from maple_monitor.dashboard.export_pages.shared import (
    render_evidence_table,
    render_source_caption,
)
from maple_monitor.sources import JOB_ANALYSIS_UNITS


bundle = require_export_bundle()
labels = {
    unit: category
    for categories in JOB_ANALYSIS_UNITS.values()
    for category, unit in categories.items()
    if not unit.endswith("_other")
}
units = sorted(set(bundle.posts["analysis_unit"]) & set(labels), key=lambda unit: labels[unit])
if not units:
    st.info("표시할 직업 게시물이 없습니다.")
    st.stop()

unit = st.selectbox("직업 선택", units, format_func=labels.__getitem__)
selection = select_window(bundle.posts, unit, hours=168, fallback_hours=720, minimum=5)
totals = engagement_totals(selection.rows)
render_source_caption(bundle, selection)

with st.container(horizontal=True):
    st.metric("게시물", f"{totals['posts']:,}건", border=True)
    st.metric("댓글", f"{totals['comments']:,}건", border=True)
    st.metric("추천", f"{totals['recommendations']:,}건", border=True)
    st.metric("조회", f"{totals['views']:,}회", border=True)

metric_options = {
    f"댓글 {totals['comments']:,}": "comments",
    f"추천 {totals['recommendations']:,}": "recommendations",
    f"조회 {totals['views']:,}": "views",
}
metric_label = st.segmented_control(
    "정렬 기준", list(metric_options), default=next(iter(metric_options))
)
if metric_label is None:
    metric_label = next(iter(metric_options))
metric = metric_options[metric_label]
st.subheader(f"{labels[unit]} 주요 게시물 · {metric_label} 순")
render_evidence_table(rank_posts(selection.rows, metric, limit=20), metric)

st.subheader("90일 상위 반응 표본 · 불만·요구·토론")
artifact = optional_analysis_artifact(bundle)
if artifact is not None and (summary := semantic_summary(artifact, unit)) is not None:
    render_semantic_summary(
        summary,
        scope_label=f"{labels[unit]} 직업 카테고리 게시물만",
    )
