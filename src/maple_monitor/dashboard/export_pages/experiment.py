from __future__ import annotations

import streamlit as st

from maple_monitor.dashboard.export_context import optional_analysis_artifact, require_export_bundle
from maple_monitor.dashboard.export_pages.shared import render_source_caption
from maple_monitor.dashboard.export_semantics import render_classification_methodology
from maple_monitor.dashboard.export_theme import render_pipeline_flow


bundle = require_export_bundle()
artifact = optional_analysis_artifact(bundle)

st.caption("MODEL SYSTEM · DOMAIN-LEXICON-V1")
st.header("커뮤니티 언어를 제품 의사결정의 근거로 바꾸는 모델")
st.write(
    "메타데이터 수집에서 끝나지 않고, 참여도가 높은 글의 본문과 댓글을 연결해 주제·의도·감성을 재현 가능한 방식으로 구조화합니다."
)
render_source_caption(bundle)

st.subheader("프로젝트의 목적과 분석 워크플로우")
render_pipeline_flow()
if artifact is not None:
    with st.container(horizontal=True):
        st.metric("분석 게시물", f"{len(artifact.posts):,}건", border=True)
        st.metric("분석 댓글", f"{len(artifact.comments):,}건", border=True)
        st.metric(
            "보안 제외", f"{int(artifact.manifest.get('quarantined_items', 0)):,}건", border=True
        )
        st.metric("모델", str(artifact.manifest.get("model_version", "")), border=True)

st.subheader("자연어 처리와 언어모델을 어디에 쓰는가")
st.markdown("""
- **직업 게시판** · 불만, 요구, 토론을 구분하고 밸런스·스킬 이슈의 근거 문장을 연결합니다.
- **자유게시판** · 큰 이슈의 주제 점유율과 작성 글–댓글 반응의 차이를 관측합니다.
- **질문과 답변** · 반복 질문과 지식 공백, 답변 댓글의 반응을 구조화합니다.
- **팁과 노하우** · 공략·정보 주제와 실제 활용 반응을 분리합니다.
""")

st.subheader("현재 모델과 고도화 경로")
st.write(
    "현재 운영 기준선은 한국어 게임 도메인 사전 기반 `domain-lexicon-v1`입니다. 결과마다 모델 버전, 신뢰도, 근거 표현을 저장하며 동일한 콘텐츠 해시는 다시 분석하지 않습니다. 저신뢰·혼합·반어 사례는 도구 접근이 차단된 언어모델 검토 큐로 보내고, 이중 라벨 골드셋이 확보되면 한국어 인코더를 미세조정해 시간 순 홀드아웃의 macro-F1과 보정 오차로 교체 여부를 판단합니다."
)
render_classification_methodology()

st.subheader("텍스트 멀티모달 모델 구조")
st.write(
    "텍스트 인코더는 제목·본문·댓글·OCR 문장을, 메타데이터 인코더는 게시판·직업·게시 시각과 정규화된 반응 변화를 처리합니다. 첨부 이미지가 있는 글은 OCR과 비전 표현을 추가하고 late fusion 기준선과 cross-attention 모델을 비교합니다. 조회·추천·댓글 수 자체는 감성 라벨로 사용하지 않습니다."
)

st.subheader("평가와 갱신 주기")
st.write(
    "메타데이터는 6시간마다 수집하고 새 ZIP을 내려받을 때 상세 수집과 추론만 증분 실행합니다. 대시보드는 완성된 분석물을 30초 이내 감지합니다. 모델 재학습은 월 1회 또는 주제·어휘·성능 드리프트가 기준을 넘을 때만 수행하며, 매 ZIP마다 학습하지 않습니다."
)

st.subheader("새 데이터가 들어왔을 때")
st.write(
    "ZIP 체크섬 확인 → 상위 표본 갱신 → 변경된 본문·댓글만 수집 → 보안 검사 → 버전형 추론 → 스키마·건수 대사 → 원자적 배포 순으로 처리합니다."
)

st.subheader("모델이 하지 않는 일")
st.write(
    "감성 결과를 자동 제재나 개인 평가에 사용하지 않습니다. 조회수가 높다는 이유로 긍정으로 분류하지 않으며, 근거 텍스트와 표본 수 없이 전체 유저 의견으로 일반화하지 않습니다."
)
