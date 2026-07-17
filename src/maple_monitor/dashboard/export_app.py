from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from maple_monitor.dashboard.export_context import export_signature, resolve_export_path
from maple_monitor.dashboard.export_theme import apply_lethe_theme


st.set_page_config(
    page_title="메이플스토리 커뮤니티 리스닝",
    page_icon=":material/analytics:",
    layout="wide",
)
apply_lethe_theme()


@st.fragment(run_every=30)
def watch_export_directory() -> None:
    """Rerun the full app when a newly published export ZIP appears."""

    path_text = os.environ.get("MAPLE_EXPORT_PATH", "").strip()
    if not path_text:
        return
    try:
        current_export = export_signature(path_text)
    except OSError:
        return
    analysis_root = os.environ.get("MAPLE_ANALYSIS_ROOT", "").strip()
    manifest_signature: tuple[str, int, int] = ("", 0, 0)
    if analysis_root:
        manifest = Path(analysis_root) / resolve_export_path(path_text).stem / "manifest.json"
        if manifest.is_file():
            stat = manifest.stat()
            manifest_signature = (str(manifest.resolve()), stat.st_mtime_ns, stat.st_size)
    current = (*current_export, *manifest_signature)
    state_key = "_maple_export_signature"
    previous = st.session_state.get(state_key)
    st.session_state[state_key] = current
    if previous is not None and previous != current:
        st.rerun()


watch_export_directory()

pages = Path(__file__).parent / "export_pages"
page = st.navigation(
    {
        "": [
            st.Page(
                pages / "overview.py",
                title="프로젝트",
                icon=":material/orbit:",
                default=True,
            )
        ],
        "게시판": [
            st.Page(pages / "jobs.py", title="직업 분석", icon=":material/groups:"),
            st.Page(pages / "free.py", title="자유게시판", icon=":material/forum:"),
            st.Page(pages / "qna.py", title="질문과 답변", icon=":material/help:"),
            st.Page(pages / "tips.py", title="팁과 노하우", icon=":material/menu_book:"),
        ],
        "모델링": [
            st.Page(
                pages / "experiment.py",
                title="NLP·멀티모달",
                icon=":material/science:",
            )
        ],
        "운영": [
            st.Page(
                pages / "operations.py",
                title="수집 상태",
                icon=":material/monitor_heart:",
            )
        ],
    },
    position="top",
)
st.title(page.title)
page.run()
