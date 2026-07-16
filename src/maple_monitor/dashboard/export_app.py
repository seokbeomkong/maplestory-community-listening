from __future__ import annotations

from pathlib import Path

import streamlit as st


st.set_page_config(
    page_title="메이플스토리 커뮤니티 현황",
    page_icon=":material/analytics:",
    layout="wide",
)

pages = Path(__file__).parent / "export_pages"
page = st.navigation(
    [
        st.Page(pages / "overview.py", title="종합 현황", icon=":material/dashboard:", default=True),
        st.Page(pages / "jobs.py", title="직업 분석", icon=":material/groups:"),
        st.Page(pages / "free.py", title="자유게시판", icon=":material/forum:"),
        st.Page(pages / "qna.py", title="질문과 답변", icon=":material/help:"),
        st.Page(pages / "tips.py", title="팁과 노하우", icon=":material/menu_book:"),
        st.Page(pages / "operations.py", title="운영 상태", icon=":material/monitor_heart:"),
    ],
    position="top",
)
st.title(f"{page.icon} {page.title}")
page.run()
