from __future__ import annotations

import streamlit as st

from maple_monitor.dashboard.export_analysis import collection_health
from maple_monitor.dashboard.export_context import require_export_bundle
from maple_monitor.dashboard.export_pages.shared import format_kst, render_source_caption


bundle = require_export_bundle()
health = collection_health(bundle)
render_source_caption(bundle)

with st.container(horizontal=True):
    st.metric("실행", f"{health.total_runs:,}건", border=True)
    st.metric("성공", f"{health.succeeded_runs:,}건", border=True)
    st.metric("실패", f"{health.failed_runs:,}건", border=True)
    st.metric("격리", f"{len(bundle.quarantine):,}건", border=True)

st.subheader("수집 실패")
if health.failed.empty:
    st.caption("실패 또는 부분 수집 실행이 없습니다.")
else:
    failed = health.failed[["job_type", "scheduled_at_slot_kst", "status", "diagnostics"]].copy()
    st.dataframe(
        failed,
        hide_index=True,
        width="stretch",
        column_config={
            "job_type": st.column_config.TextColumn("작업"),
            "scheduled_at_slot_kst": st.column_config.DatetimeColumn(
                "예약 시각", format="YYYY.MM.DD HH:mm"
            ),
            "status": st.column_config.TextColumn("상태"),
            "diagnostics": st.column_config.TextColumn("진단"),
        },
    )

st.subheader("검증 상태")
st.caption(f"체크섬 {sum(bundle.checksums.values())}/{len(bundle.checksums)}개 일치")
if health.latest_slot is not None:
    st.caption(f"최신 사실 시각 {format_kst(health.latest_slot)}")
