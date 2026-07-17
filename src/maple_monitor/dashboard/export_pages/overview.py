from __future__ import annotations

import streamlit as st

from maple_monitor.dashboard.export_analysis import collection_health, job_comparison
from maple_monitor.dashboard.export_charts import job_constellation
from maple_monitor.dashboard.export_context import require_export_bundle
from maple_monitor.dashboard.export_pages.shared import render_source_caption
from maple_monitor.dashboard.export_presentation import portfolio_snapshot
from maple_monitor.dashboard.export_theme import LETHE_PROMOTION_URL, render_lethe_hero


bundle = require_export_bundle()
snapshot = portfolio_snapshot(bundle)
totals = snapshot["totals"]
health = collection_health(bundle)

render_lethe_hero()
st.caption("MAPLE COMMUNITY LISTENING · DATA PORTFOLIO")
st.header("커뮤니티의 목소리를 검증 가능한 데이터로")
st.write(
    "메이플스토리 인벤의 게시판별 성격을 구분하고, 직업 유저의 요구와 "
    "전체 커뮤니티의 큰 이슈를 서로 다른 관점으로 읽는 분석 프로젝트입니다."
)
render_source_caption(bundle)

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
                "effective_hours": "적용 시간",
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
                    "적용 시간",
                ]
            ],
            hide_index=True,
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

st.subheader("다음 실험: 불만·요구·토론을 구조화하기")
st.write(
    "현재 ZIP에는 본문과 댓글, 감성 라벨이 없습니다. 그래서 보유하지 않은 결과를 "
    "만들지 않고, 참여도가 높은 게시물을 표본으로 삼는 라벨링·모델 평가 계획을 "
    "별도 페이지에 공개합니다."
)

st.subheader("데이터 한계")
st.info(
    "현재 단계에서는 제목과 공개 반응 지표만 분석합니다. 제목만으로 감성이나 의도를 "
    "단정하지 않으며, 조회·추천·댓글은 관심의 크기이지 긍정·부정의 증거가 아닙니다.",
    icon=":material/info:",
)
st.markdown(f"[공식 레테 비주얼 출처 확인]({LETHE_PROMOTION_URL})")
