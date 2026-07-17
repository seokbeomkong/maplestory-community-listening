from __future__ import annotations

import streamlit as st


LETHE_PROMOTION_URL = (
    "https://maplestory.nexon.com/promotion/event/2026/20260618/event01"
)
LETHE_HERO_URL = (
    "https://lwi.nexon.com/maplestory/2026/0618_lethe_A0ECF482FBC7C753/"
    "bg1_413b4f4fbeab575f.jpg"
)


def apply_lethe_theme() -> None:
    """Add a restrained Lethe-inspired presentation layer to native Streamlit."""

    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600&family=Noto+Serif+KR:wght@600;700&display=swap');
        html, body, [class*="st-"] { font-family: 'Noto Sans KR', sans-serif; }
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
          position: relative; min-height: 330px; border-radius: 12px; overflow: hidden;
          border: 1px solid rgba(224, 200, 120, .28);
          background-image: linear-gradient(90deg, rgba(7,9,21,.96) 0%, rgba(7,9,21,.64) 45%, rgba(7,9,21,.10) 78%),
                            url('https://lwi.nexon.com/maplestory/2026/0618_lethe_A0ECF482FBC7C753/bg1_413b4f4fbeab575f.jpg');
          background-size: cover; background-position: center 18%;
          box-shadow: 0 24px 70px rgba(0,0,0,.30);
          margin: .3rem 0 1.4rem;
        }
        .lethe-hero__copy { position: absolute; left: 2.2rem; bottom: 2.1rem; max-width: 34rem; }
        .lethe-hero__eyebrow { color: #d8c47c; font-size: .72rem; letter-spacing: .2em; }
        .lethe-hero__title { margin: .55rem 0 .65rem; color: #fff; font: 700 2.05rem/1.25 'Noto Serif KR', serif; }
        .lethe-hero__text { color: #cfceda; line-height: 1.7; font-size: .93rem; }
        @media (max-width: 700px) {
          .lethe-hero { min-height: 390px; background-position: 62% center; }
          .lethe-hero__copy { left: 1.2rem; right: 1.2rem; bottom: 1.25rem; }
          .lethe-hero__title { font-size: 1.55rem; }
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
    st.caption(
        "공식 비주얼: 메이플스토리 〈서약의 지배자, 레테〉 프로모션 · "
        "© NEXON Korea"
    )
