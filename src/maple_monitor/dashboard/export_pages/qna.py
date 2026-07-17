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
selection = select_window(bundle.posts, "qna", hours=168)
render_source_caption(bundle, selection)

st.subheader("댓글 0건 질문")
zero_comment = selection.rows.loc[selection.rows["comments"] == 0].sort_values(
    ["published_at", "post_id"], ascending=[False, False]
)
render_evidence_table(rank_posts(zero_comment, "comments", limit=20), "comments")
st.caption("댓글 수만 확인한 목록이며 해결 여부를 의미하지 않습니다.")

st.subheader("댓글이 많은 질문")
render_evidence_table(rank_posts(selection.rows, "comments", limit=20), "comments")

artifact = optional_analysis_artifact(bundle)
if artifact is not None and (summary := semantic_summary(artifact, "qna")) is not None:
    st.subheader("90일 상위 반응 표본 · 반복 질문과 댓글 반응")
    render_semantic_summary(summary, scope_label="질문과 답변 게시물만")
