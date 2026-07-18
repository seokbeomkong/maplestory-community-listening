from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from maple_monitor.dashboard.export_analysis import source_period
from maple_monitor.local.artifacts import AnalysisArtifact
from maple_monitor.local.detail_parser import GENERAL_ANALYSIS_UNITS
from maple_monitor.local.opinion import load_analysis_rules


_SENTIMENT = {
    "positive": "긍정",
    "neutral": "중립",
    "negative": "부정",
    "mixed": "혼합",
}
_INTENT = {
    "complaint": "불만",
    "request": "요구",
    "debate": "토론",
    "question": "질문",
    "praise": "칭찬",
    "information": "정보",
}
_SELECTION_REASON = {
    "comments": "댓글 상위",
    "recommendations": "추천 상위",
    "views": "조회 상위",
}


@dataclass(frozen=True)
class DistributionRow:
    label: str
    count: int
    share: float


@dataclass(frozen=True)
class SemanticSummary:
    rows: pd.DataFrame
    comments: pd.DataFrame
    analysis_unit: str
    model_version: str
    generated_at: str
    selection_policy: Mapping[str, object]


def semantic_summary(artifact: AnalysisArtifact, analysis_unit: str) -> SemanticSummary | None:
    rows = artifact.posts.loc[artifact.posts["analysis_unit"] == analysis_unit].copy()
    if rows.empty:
        return None
    keys = rows[["board_id", "post_id"]].drop_duplicates()
    comments = artifact.comments.merge(keys, on=["board_id", "post_id"], how="inner")
    policy = artifact.manifest.get("selection_policy", {})
    return SemanticSummary(
        rows=rows,
        comments=comments,
        analysis_unit=analysis_unit,
        model_version=str(artifact.manifest.get("model_version", "")),
        generated_at=str(artifact.manifest.get("generated_at_kst", "")),
        selection_policy=policy if isinstance(policy, Mapping) else {},
    )


def distribution_rows(
    values: pd.Series, labels: Mapping[str, str] | None = None
) -> tuple[DistributionRow, ...]:
    mapped = values.map(labels).fillna(values) if labels is not None else values
    counts = mapped.value_counts()
    total = int(counts.sum())
    return tuple(
        DistributionRow(str(label), int(count), float(count / total))
        for label, count in counts.items()
    )


def _negative_or_mixed_share(rows: pd.DataFrame, column: str) -> float:
    return float(rows[column].isin({"negative", "mixed"}).mean()) if len(rows) else 0.0


def _display_evidence_terms(values: pd.Series) -> pd.Series:
    return values.fillna("").replace("", "직접 표현 없음")


def _render_distribution(
    title: str, values: pd.Series, labels: Mapping[str, str] | None = None
) -> None:
    st.markdown(f"**{title}**")
    for row in distribution_rows(values, labels):
        st.progress(
            row.share,
            text=f"{row.label} · {row.count:,}건 · {row.share:.0%}",
        )


def render_classification_methodology() -> None:
    rules = load_analysis_rules()
    with st.expander(
        "분류 기준과 해석 방법",
        icon=":material/rule:",
    ):
        st.markdown(
            """
**주제**는 제목과 본문에서 주제별 표현이 나온 횟수를 비교합니다. 가장 많이
일치한 주제를 선택하며, 근거가 없으면 `커뮤니티`로 둡니다.

**작성 의도**는 제목과 본문에서 요구·불만·토론·질문·칭찬·정보 표현의 일치
수를 비교합니다. 동률은 고정된 사전 순서를 적용하고, 근거가 없으면 `정보`로 둡니다.

**작성 글 감성**은 본문만 사용합니다. 긍정 표현만 있으면 긍정, 부정 표현만
있으면 부정, 둘 다 있으면 혼합, 모두 없으면 중립입니다.

**댓글 반응**은 댓글마다 같은 감성 규칙을 적용한 뒤 중립을 제외한 최빈 범주로
정합니다. 최빈 범주가 동률이면 혼합, 감성 표현이 없으면 중립입니다.
"""
        )
        criteria = pd.DataFrame(
            [
                {
                    "구분": "감성·긍정",
                    "대표 표현": " · ".join(rules.positive[:8]),
                },
                {
                    "구분": "감성·부정",
                    "대표 표현": " · ".join(rules.negative[:8]),
                },
                *(
                    {
                        "구분": f"의도·{_INTENT.get(label, label)}",
                        "대표 표현": " · ".join(terms[:6]),
                    }
                    for label, terms in rules.intents.items()
                ),
                *(
                    {
                        "구분": f"주제·{label}",
                        "대표 표현": " · ".join(terms[:6]),
                    }
                    for label, terms in rules.topics.items()
                ),
            ]
        )
        st.dataframe(criteria, hide_index=True, width="stretch")
        st.caption(
            "댓글·추천·조회는 분석할 게시물을 고르는 데만 사용하며, 감성 라벨에는 "
            "사용하지 않습니다. 이 결과는 사전 기반 기준선이며 반어·은어는 근거 "
            "게시물과 함께 검토합니다."
        )


def render_semantic_summary(
    summary: SemanticSummary,
    *,
    scope_label: str,
) -> None:
    rows = summary.rows
    period = source_period(rows)
    policy = summary.selection_policy
    is_general = summary.analysis_unit in GENERAL_ANALYSIS_UNITS
    limit_key = "general_per_metric" if is_general else "job_per_metric"
    window_days = int(policy.get("window_days", 90))
    per_metric = int(policy.get(limit_key, 1))

    st.caption(
        f"분석 범위 · {scope_label} · 최근 {window_days}일 댓글·추천·조회 각 상위 "
        f"{per_metric}건 · 중복 게시물 제거"
    )
    with st.container(horizontal=True):
        st.metric("분석 게시물", f"{len(rows):,}건", border=True)
        st.metric("분석 댓글", f"{len(summary.comments):,}건", border=True)
        st.metric(
            "부정·혼합 작성 글",
            f"{_negative_or_mixed_share(rows, 'body_sentiment'):.0%}",
            border=True,
        )
        st.metric(
            "부정·혼합 댓글 반응",
            f"{_negative_or_mixed_share(rows, 'comment_reaction'):.0%}",
            border=True,
        )
    st.caption(
        f"{period.label} · {summary.model_version} · 분석 갱신 {summary.generated_at[:16]} KST"
    )
    if len(rows) < 5:
        st.caption("표본이 5건 미만이므로 비율은 방향성 확인에만 사용합니다.")

    first_row = st.columns(2)
    with first_row[0].container(border=True, height="stretch"):
        _render_distribution("주요 주제", rows["topic"])
    with first_row[1].container(border=True, height="stretch"):
        _render_distribution("작성 의도", rows["intent"], _INTENT)
    second_row = st.columns(2)
    with second_row[0].container(border=True, height="stretch"):
        _render_distribution("작성 글 감성", rows["body_sentiment"], _SENTIMENT)
    with second_row[1].container(border=True, height="stretch"):
        _render_distribution("댓글 반응", rows["comment_reaction"], _SENTIMENT)

    render_classification_methodology()

    evidence_columns = [
        "title",
        "selection_reason",
        "topic",
        "intent",
        "body_sentiment",
        "comment_reaction",
        "evidence_terms",
        "analyzed_comment_count",
        "views",
        "recommendations",
        "source_url",
    ]
    evidence = rows[evidence_columns].copy()
    evidence["selection_reason"] = (
        evidence["selection_reason"].map(_SELECTION_REASON).fillna(evidence["selection_reason"])
    )
    evidence["intent"] = evidence["intent"].map(_INTENT).fillna(evidence["intent"])
    evidence["body_sentiment"] = (
        evidence["body_sentiment"].map(_SENTIMENT).fillna(evidence["body_sentiment"])
    )
    evidence["comment_reaction"] = (
        evidence["comment_reaction"].map(_SENTIMENT).fillna(evidence["comment_reaction"])
    )
    evidence["evidence_terms"] = _display_evidence_terms(evidence["evidence_terms"])
    st.dataframe(
        evidence,
        hide_index=True,
        column_config={
            "title": st.column_config.TextColumn("근거 게시물", pinned=True),
            "selection_reason": "표본 선정",
            "topic": "주제",
            "intent": "의도",
            "body_sentiment": "작성 글 감성",
            "comment_reaction": "댓글 반응",
            "evidence_terms": "감성 근거 표현",
            "analyzed_comment_count": "분석 댓글",
            "views": "조회",
            "recommendations": "추천",
            "source_url": st.column_config.LinkColumn("원문", display_text="열기"),
        },
        width="stretch",
    )
