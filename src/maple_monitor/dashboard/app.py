from __future__ import annotations

import streamlit as st
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from maple_monitor.dashboard.pages.cumulative import render
from maple_monitor.db import create_engine_from_env


st.set_page_config(page_title="누적 상위 50", layout="wide")


@st.cache_resource
def _dashboard_engine() -> Engine:
    return create_engine_from_env()


try:
    _engine = _dashboard_engine()
except (KeyError, SQLAlchemyError):
    st.error("데이터베이스 설정을 확인해 주세요.")
else:
    render(_engine)
