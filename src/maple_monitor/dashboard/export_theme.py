from __future__ import annotations

import streamlit as st


LETHE_PROMOTION_URL = "https://maplestory.nexon.com/promotion/event/2026/20260618/event01"
LETHE_HERO_URL = (
    "https://lwi.nexon.com/maplestory/2026/0618_lethe_A0ECF482FBC7C753/bg1_413b4f4fbeab575f.jpg"
)


def apply_lethe_theme() -> None:
    """Add a restrained Lethe-inspired presentation layer to native Streamlit."""

    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600&family=Noto+Serif+KR:wght@600;700&display=swap');
        h1, h2, h3 { font-family: 'Noto Serif KR', serif !important; letter-spacing: -0.025em; }
        [data-testid="stAppViewContainer"] {
          background:
            radial-gradient(circle at 86% 8%, rgba(91, 83, 145, .18), transparent 26rem),
            linear-gradient(180deg, #090b19 0%, #0d1021 100%);
        }
        [data-testid="stHeader"] { background: rgba(9, 11, 25, .82); }
        [data-testid="stMetric"] {
          background: linear-gradient(145deg, rgba(27, 30, 52, .92), rgba(16, 18, 35, .94));
          border-color: rgba(216, 196, 124, .22) !important;
          box-shadow: inset 0 1px 0 rgba(255,255,255,.025), 0 10px 28px rgba(0,0,0,.12);
        }
        [data-testid="stMetricValue"] { color: #f2e7ba; }
        div[data-testid="stExpander"] { border-color: rgba(216, 196, 124, .18); }
        .lethe-hero {
          position: relative; min-height: 410px; border-radius: 12px; overflow: hidden;
          border: 1px solid rgba(224, 200, 120, .28);
          background-image: linear-gradient(90deg, rgba(7,9,21,.96) 0%, rgba(7,9,21,.64) 45%, rgba(7,9,21,.10) 78%),
                            url('https://lwi.nexon.com/maplestory/2026/0618_lethe_A0ECF482FBC7C753/bg1_413b4f4fbeab575f.jpg');
          background-size: cover; background-position: 52% 42%;
          box-shadow: 0 24px 70px rgba(0,0,0,.30);
          margin: .3rem 0 1.4rem;
        }
        .lethe-hero__copy { position: absolute; left: 2.2rem; bottom: 2.4rem; max-width: 30rem; }
        .lethe-hero__eyebrow { color: #d8c47c; font-size: .72rem; letter-spacing: .2em; }
        .lethe-hero__title { margin: .55rem 0 .65rem; color: #fff; font: 700 2.05rem/1.25 'Noto Serif KR', serif; }
        .lethe-hero__text { color: #cfceda; line-height: 1.7; font-size: .93rem; }
        .pipeline-flow { display:grid; grid-template-columns:repeat(5,1fr); gap:.6rem; margin:1rem 0 1.5rem; }
        .pipeline-step { position:relative; min-height:7.4rem; padding:1rem; border-top:2px solid #d8c47c;
          background:linear-gradient(180deg,rgba(35,39,69,.86),rgba(17,20,39,.72)); }
        .pipeline-step b { display:block; color:#f2e7ba; margin:.35rem 0; }
        .pipeline-step span { color:#9fa2b8; font-size:.77rem; letter-spacing:.08em; }
        .pipeline-step p { color:#c9cad6; font-size:.82rem; line-height:1.5; margin:0; }
        @media (max-width: 700px) {
          .lethe-hero { min-height: 440px; background-position: 57% 42%; }
          .lethe-hero__copy { left: 1.2rem; right: 1.2rem; bottom: 1.25rem; }
          .lethe-hero__title { font-size: 1.55rem; }
          .pipeline-flow { grid-template-columns:1fr; }
        }
        @media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_lethe_hero() -> None:
    st.markdown(
        """
        <div class="lethe-hero" role="img" aria-label="메이플스토리 공식 레테 프로모션 배경">
          <div class="lethe-hero__copy">
            <div class="lethe-hero__eyebrow">COMMUNITY OBSERVATION RECORD · 2026</div>
            <div class="lethe-hero__title">수많은 목소리 사이에서<br>검증할 수 있는 신호를 찾다</div>
            <div class="lethe-hero__text">게시판의 성격을 존중하고, 관심의 크기와 대화의 의미를 분리해 기록합니다.</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("공식 비주얼: 메이플스토리 〈서약의 지배자, 레테〉 프로모션 · © NEXON Korea")


def render_pipeline_flow() -> None:
    st.markdown(
        """
        <section class="pipeline-flow" aria-label="커뮤니티 반응 분석 워크플로우">
          <article class="pipeline-step"><span>01 · COLLECT</span><b>6시간 수집</b><p>게시판·직업·시각과 반응 지표를 누적합니다.</p></article>
          <article class="pipeline-step"><span>02 · SELECT</span><b>상위 표본 선별</b><p>댓글·추천·조회 상위 글을 지표별로 추출합니다.</p></article>
          <article class="pipeline-step"><span>03 · ENRICH</span><b>본문·댓글 수집</b><p>원문과 댓글을 정제하고 안전성 검사를 통과시킵니다.</p></article>
          <article class="pipeline-step"><span>04 · INFER</span><b>주제·의도·감성</b><p>작성 글과 댓글 반응을 분리해 추론합니다.</p></article>
          <article class="pipeline-step"><span>05 · SERVE</span><b>대시보드 갱신</b><p>검증된 결과를 30초 이내 화면에 반영합니다.</p></article>
        </section>
        """,
        unsafe_allow_html=True,
    )
