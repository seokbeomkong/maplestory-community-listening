from __future__ import annotations

from pathlib import Path

import streamlit as st


st.set_page_config(
    page_title="메이플스토리 커뮤니티 현황",
    page_icon=":material/analytics:",
    layout="wide",
)

page = st.navigation(
    [
        st.Page(
            Path(__file__).parent / "export_pages" / "overview.py",
            title="종합 현황",
            icon=":material/dashboard:",
            default=True,
        )
    ],
    position="top",
)
st.title(f"{page.icon} {page.title}")
page.run()
