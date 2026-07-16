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

st.subheader("질문 주제·지식 공백 분석 상태")
render_semantic_state(semantic_availability(bundle))
