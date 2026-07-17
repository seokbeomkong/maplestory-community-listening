from __future__ import annotations

import streamlit as st

from maple_monitor.dashboard.export_context import require_export_bundle
from maple_monitor.dashboard.export_experiment import experiment_blueprint
from maple_monitor.dashboard.export_pages.shared import render_source_caption


bundle = require_export_bundle()
blueprint = experiment_blueprint()

st.caption("EXPERIMENT DESIGN · NOT YET EXECUTED")
st.header("반응 지표에서 유저의 의도까지")
st.write(
    "현재 확인 가능한 것은 관심의 크기입니다. 다음 단계에서는 본문과 댓글을 확보해 "
    "직업 게시판의 불만·요구·토론과 다른 게시판의 주요 이슈·반응을 분리해 측정합니다."
)
render_source_caption(bundle)
st.warning(
    f"결과 상태: {blueprint['result_status']}. 아래 수치는 성능 결과가 아니라 실행 규약입니다.",
    icon=":material/science:",
)

st.subheader("1 · 표본 설계")
sampling = blueprint["sampling"]
st.write(
    f"분석 단위는 **{sampling['unit']}**입니다. "
    f"{', '.join(sampling['strata'])}로 층화하고, {sampling['rule']}합니다. "
    f"재현용 난수 시드는 `{sampling['seed']}`로 고정합니다."
)

st.subheader("2 · 두 단계 라벨 체계")
intent, topic = st.columns(2)
with intent:
    st.markdown("**대화 의도**")
    st.write(" · ".join(blueprint["intent_labels"]))
with topic:
    st.markdown("**이슈 주제**")
    st.write(" · ".join(blueprint["topic_labels"]))
st.caption(
    "직업 게시판은 의도와 직업별 세부 이슈를 함께 보고, 자유·질문·팁 게시판은 "
    "게시판 목적에 맞춰 주제와 반응의 관계를 우선 해석합니다."
)

st.subheader("3 · 라벨 품질")
quality = blueprint["label_quality"]
st.write(
    f"{quality['gold_set']}. 일치도는 {quality['agreement']}로 확인하고, "
    f"{quality['guide']}합니다."
)

st.subheader("4 · 기준선과 소형 언어모델")
for index, model in enumerate(blueprint["models"], start=1):
    st.markdown(f"**{index}. {model}**")
st.write(
    "복잡한 모델이 실제로 나아졌는지 기준선과 같은 분할·같은 라벨 체계에서 비교합니다."
)

st.subheader("5 · 일반화 평가")
evaluation = blueprint["evaluation"]
with st.container(horizontal=True):
    st.metric("주 지표", evaluation["primary_metric"], border=True)
    st.metric("검증 분할", f"{len(evaluation['splits'])}종", border=True)
    st.metric("보조 진단", f"{len(evaluation['secondary_metrics'])}종", border=True)
st.write("검증 분할: " + " · ".join(evaluation["splits"]))
st.write("보조 진단: " + " · ".join(evaluation["secondary_metrics"]))

st.subheader("채용 직무와 연결되는 산출물")
st.write(
    "데이터셋 설계·정제·품질 검수, 가설과 실험 설계, 모델 학습·평가, "
    "오류 분석과 개선 기록을 하나의 재현 가능한 실험 보고서로 남깁니다."
)
