from __future__ import annotations

import pandas as pd

from maple_monitor.dashboard.export_semantics import (
    _SENTIMENT,
    _display_evidence_terms,
    _negative_or_mixed_share,
    distribution_rows,
)


def test_negative_or_mixed_share_includes_ambivalent_reactions() -> None:
    rows = pd.DataFrame({"sentiment": ["negative", "mixed", "positive", "neutral"]})

    assert _negative_or_mixed_share(rows, "sentiment") == 0.5


def test_distribution_rows_returns_ranked_exact_counts_and_shares() -> None:
    rows = distribution_rows(pd.Series(["negative", "negative", "positive"]), _SENTIMENT)

    assert [(row.label, row.count, row.share) for row in rows] == [
        ("부정", 2, 2 / 3),
        ("긍정", 1, 1 / 3),
    ]


def test_missing_evidence_terms_have_a_reader_facing_label() -> None:
    values = _display_evidence_terms(pd.Series([None, "", "너프 · 문제"]))

    assert values.tolist() == ["직접 표현 없음", "직접 표현 없음", "너프 · 문제"]
