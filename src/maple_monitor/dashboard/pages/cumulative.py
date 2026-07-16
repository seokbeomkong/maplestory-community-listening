from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from maple_monitor.dashboard.queries import load_cumulative_top
from maple_monitor.sources import JOB_ANALYSIS_UNITS, SOURCES


_TABLE_COLUMNS = ["rank", "title", "metric_value", "published_at", "source_url"]

def _analysis_unit_labels() -> dict[str, str]:
    labels: dict[str, str] = {}
    for source in SOURCES:
        if source.kind == "job":
            for category, analysis_unit in JOB_ANALYSIS_UNITS[source.board_id].items():
                labels[analysis_unit] = (
                    f"{source.name} 기타" if analysis_unit.endswith("_other") else category
                )
        elif source.fixed_analysis_unit is not None:
            labels[source.fixed_analysis_unit] = source.name
    return labels


_ANALYSIS_UNIT_LABELS = _analysis_unit_labels()
_METRIC_LABELS = {
    "recommendations": "추천",
    "comments": "댓글",
    "views": "조회",
}


def _provenance_caption(frame: pd.DataFrame) -> str:
    as_of = frame.iloc[0]["as_of_slot_kst"]
    config_version = str(frame.iloc[0]["config_version"])
    as_of_text = as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of)
    return f"기준 시각: {as_of_text} · 설정 버전: {config_version[:12]}"


def render(engine: object) -> None:
    st.header("누적 상위 50")
    st.caption("최근 90일 누적 순위 · 급상승 순위와 별도 집계")
    analysis_unit = st.selectbox(
        "분석 단위",
        list(_ANALYSIS_UNIT_LABELS),
        format_func=_ANALYSIS_UNIT_LABELS.__getitem__,
        key="cumulative_unit",
    )
    metric = st.selectbox(
        "기준",
        ["recommendations", "comments", "views"],
        format_func=_METRIC_LABELS.__getitem__,
        key="cumulative_metric",
    )

    try:
        frame = load_cumulative_top(engine, analysis_unit, metric)  # type: ignore[arg-type]
    except SQLAlchemyError:
        st.error("데이터를 불러오지 못했습니다. 데이터베이스 설정을 확인해 주세요.")
        return

    if frame.empty:
        st.info("표시할 누적 순위 데이터가 없습니다.")
        return

    st.caption(_provenance_caption(frame))
    st.dataframe(
        frame[_TABLE_COLUMNS],
        hide_index=True,
        width="stretch",
        column_config={
            "rank": st.column_config.NumberColumn("순위", format="%d"),
            "title": st.column_config.TextColumn("제목"),
            "metric_value": st.column_config.NumberColumn("값", format="%d"),
            "published_at": st.column_config.DatetimeColumn("게시 시각"),
            "source_url": st.column_config.LinkColumn("원문", display_text="열기"),
        },
    )
