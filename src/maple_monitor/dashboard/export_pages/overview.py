from __future__ import annotations

import streamlit as st

from maple_monitor.dashboard.export_analysis import collection_health, job_comparison
from maple_monitor.dashboard.export_charts import job_constellation
from maple_monitor.dashboard.export_context import require_export_bundle
from maple_monitor.dashboard.export_pages.shared import render_source_caption
from maple_monitor.dashboard.export_presentation import portfolio_snapshot
from maple_monitor.dashboard.export_theme import (
    LETHE_PROMOTION_URL,
    render_lethe_hero,
    render_pipeline_flow,
)


bundle = require_export_bundle()
snapshot = portfolio_snapshot(bundle)
totals = snapshot["totals"]
health = collection_health(bundle)

render_lethe_hero()
st.caption("MAPLE COMMUNITY LISTENING · DATA PORTFOLIO")
st.header("실시간 유저 반응 관측")
st.write(
    "메이플스토리 유저의 반응을 제품과 라이브 운영 의사결정에 활용할 수 있는 신호로 "
    "전환하기 위해 시작했습니다. 게시판별 대화 목적을 구분하고, 관심의 크기와 감성을 "
    "분리해 관측합니다."
)
render_source_caption(bundle)

st.subheader("분석 워크플로우")
render_pipeline_flow()

with st.container(horizontal=True):
    st.metric("수집 게시물", f"{totals['posts']:,}건", border=True)
    st.metric("댓글", f"{totals['comments']:,}개", border=True)
    st.metric("추천", f"{totals['recommendations']:,}개", border=True)
    st.metric("조회", f"{totals['views']:,}회", border=True)

st.subheader("직업 별자리")
st.write(
    "점 하나가 직업 하나입니다. 오른쪽일수록 수집 글이 많고, 위쪽일수록 "
    "글 하나에 토론이 많이 붙었습니다. 원의 크기는 조회, 색은 게시물당 추천을 뜻합니다."
)
comparison = job_comparison(bundle.posts)
if comparison.empty:
    st.caption("비교할 직업 게시물이 없습니다.")
else:
    st.altair_chart(job_constellation(comparison), width="stretch")
    expanded_jobs = int(comparison["fallback_reason"].notna().sum())
    if expanded_jobs:
        st.caption(f"7일 표본 부족으로 30일 확장 · {expanded_jobs}개 직업")
    with st.expander("정확한 수치와 적용 기간 보기"):
        table = comparison.rename(
            columns={
                "job": "직업",
                "sample_size": "게시물",
                "total_comments": "댓글",
                "comments_per_post": "게시물당 댓글",
                "total_recommendations": "추천",
                "recommendations_per_post": "게시물당 추천",
                "total_views": "조회",
                "views_per_post": "게시물당 조회",
                "analysis_period": "적용 기간",
            }
        )
        st.dataframe(
            table[
                [
                    "직업",
                    "게시물",
                    "댓글",
                    "게시물당 댓글",
                    "추천",
                    "게시물당 추천",
                    "조회",
                    "게시물당 조회",
                    "적용 기간",
                ]
            ],
            hide_index=True,
            column_config={
                "게시물당 댓글": st.column_config.NumberColumn(format="%.1f"),
                "게시물당 추천": st.column_config.NumberColumn(format="%.1f"),
                "게시물당 조회": st.column_config.NumberColumn(format="%.1f"),
            },
            width="stretch",
        )

st.subheader("증거를 먼저 확인하는 분석")
proof = snapshot["source"]
with st.container(horizontal=True):
    st.metric(
        "체크섬 검증",
        f"{proof['checksums_verified']}/{proof['checksums_total']}",
        border=True,
    )
    st.metric("수집 성공률", f"{health.success_rate:.0%}", border=True)
    st.metric("분석 단위", f"{bundle.posts['analysis_unit'].nunique():,}개", border=True)
st.write(
    "모든 표와 차트는 원문 링크, 관측 시각, 게시물·댓글·추천·조회 원시 지표로 "
    "되돌아갈 수 있게 구성했습니다. 합성 점수는 사용하지 않습니다."
)

st.subheader("분석 원칙")
st.write(
    "조회·추천·댓글은 표본 우선순위를 정하는 관심 지표로만 사용합니다. 감성은 본문과 댓글 텍스트에서 각각 추론하며, 작성자의 입장과 댓글 반응을 하나의 점수로 합치지 않습니다."
)
st.markdown(f"[공식 레테 비주얼 출처 확인]({LETHE_PROMOTION_URL})")
