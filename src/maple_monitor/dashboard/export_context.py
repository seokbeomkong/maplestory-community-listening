from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from maple_monitor.dashboard.export_data import (
    ExportArchiveError,
    ExportBundle,
    load_export_archive,
)


@st.cache_data(show_spinner="검증된 내보내기를 불러오는 중입니다")
def _load_current_export(path_text: str, modified_ns: int, size: int) -> ExportBundle:
    del modified_ns, size
    return load_export_archive(Path(path_text))


def require_export_bundle() -> ExportBundle:
    path_text = os.environ.get("MAPLE_EXPORT_PATH", "").strip()
    if not path_text:
        st.error("환경 변수 MAPLE_EXPORT_PATH에 검증된 ZIP 경로를 설정해 주세요.")
        st.stop()
    try:
        path = Path(path_text)
        stat = path.stat()
        bundle = _load_current_export(str(path), stat.st_mtime_ns, stat.st_size)
        if bundle.posts.empty:
            st.warning("검증된 내보내기에 게시물 데이터가 없습니다.")
            st.stop()
        return bundle
    except (OSError, ExportArchiveError):
        st.error("내보내기 ZIP을 안전하게 불러오지 못했습니다. 파일과 체크섬을 확인해 주세요.")
        st.stop()
