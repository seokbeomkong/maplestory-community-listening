from __future__ import annotations

import pandas as pd
import streamlit as st

from maple_monitor.dashboard.export_analysis import WindowSelection, source_period
from maple_monitor.dashboard.export_data import ExportBundle


_METRIC_LABELS = {"views": "조회", "recommendations": "추천", "comments": "댓글"}


def format_kst(value: object) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return timestamp.tz_convert("Asia/Seoul").strftime("%Y.%m.%d %H:%M KST")


def render_source_caption(bundle: ExportBundle, selection: WindowSelection | None = None) -> None:
    latest = bundle.posts["observed_at_slot_kst"].max()
    rows = selection.rows if selection is not None else bundle.posts
    parts = [
        source_period(rows).label,
        f"최신 수집 {format_kst(latest)}",
        f"게시물 {len(bundle.posts):,}건",
    ]
    if selection is not None:
        parts.append(f"표본 {len(selection.rows):,}건")
        parts.append(f"기간 {selection.effective_hours // 24}일")
        if selection.fallback_reason:
            parts.append(selection.fallback_reason)
    st.caption(" · ".join(parts))


def render_evidence_table(rows: pd.DataFrame, metric: str) -> None:
    if rows.empty:
        st.caption("해당 기간에 표시할 게시물이 없습니다.")
        return
    labels = dict(_METRIC_LABELS)
    labels[metric] = f"{labels[metric]} ↓"
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        column_config={
            "title": st.column_config.TextColumn("제목", pinned=True),
            "comments": st.column_config.NumberColumn(labels["comments"], format="%d"),
            "recommendations": st.column_config.NumberColumn(
                labels["recommendations"], format="%d"
            ),
            "views": st.column_config.NumberColumn(labels["views"], format="%d"),
            "published_at": st.column_config.DatetimeColumn("게시 시각", format="YYYY.MM.DD HH:mm"),
            "source_url": st.column_config.LinkColumn("원문", display_text="열기"),
        },
    )
