from __future__ import annotations

import json

import pandas as pd

from maple_monitor.local.detail_parser import (
    parse_article,
    parse_comments,
    select_detail_candidates,
)


def test_article_and_comments_are_reduced_to_analysis_text() -> None:
    article = parse_article(
        b'<html><h1>Title</h1><div id="powerbbsContent"><b>Skill</b> improvement needed</div></html>'
    )
    payload = json.dumps(
        {
            "message": 1,
            "cmtcount": 2,
            "commentlist": [
                {
                    "list": [
                        {
                            "__attr__": {"cmtidx": 10, "cmtpidx": 10},
                            "o_date": "2026-07-17 01:00:00",
                            "o_comment": "좋아요&amp;nbsp;",
                        },
                        {
                            "__attr__": {"cmtidx": 11, "cmtpidx": 10},
                            "o_date": "2026-07-17 01:01:00",
                            "o_comment": "&lt;b&gt;수정 필요&lt;/b&gt;",
                        },
                    ]
                }
            ],
        },
        ensure_ascii=False,
    ).encode()

    comments = parse_comments(payload)

    assert article.body == "Skill improvement needed"
    assert [item.text for item in comments.comments] == ["좋아요", "수정 필요"]
    assert comments.comments[1].parent_id == 10
    assert comments.complete is True


def test_candidate_selection_covers_each_unit_and_metric_without_duplicates() -> None:
    rows = []
    for unit, board_id in (("hero", 2294), ("free", 5974)):
        for index in range(3):
            rows.append(
                {
                    "analysis_unit": unit,
                    "board_id": board_id,
                    "post_id": board_id * 10 + index,
                    "published_at": pd.Timestamp("2026-07-17", tz="Asia/Seoul")
                    - pd.Timedelta(int(index), unit="D"),
                    "comments": [30, 1, 2][index],
                    "recommendations": [1, 40, 2][index],
                    "views": [1, 2, 500][index],
                    "source_url": "https://www.inven.co.kr/board/maple/1/1",
                }
            )
    selected = select_detail_candidates(pd.DataFrame(rows), window_days=90, per_metric=1)

    assert len(selected) == 6
    assert not selected.duplicated(["board_id", "post_id"]).any()
    assert set(selected["selection_reason"]) == {"comments", "recommendations", "views"}


def test_candidate_selection_applies_limits_inside_each_analysis_unit() -> None:
    rows = []
    for unit, board_id, limit in (("hero", 2294, 2), ("free", 5974, 3)):
        size = limit * 3
        for index in range(size):
            metric_group = index // limit
            metric_rank = index % limit
            rows.append(
                {
                    "analysis_unit": unit,
                    "board_id": board_id,
                    "post_id": board_id * 100 + index,
                    "published_at": pd.Timestamp("2026-07-17", tz="Asia/Seoul"),
                    "comments": 100 - metric_rank if metric_group == 0 else 0,
                    "recommendations": 100 - metric_rank if metric_group == 1 else 0,
                    "views": 100 - metric_rank if metric_group == 2 else 0,
                    "source_url": "https://www.inven.co.kr/board/maple/1/1",
                }
            )

    selected = select_detail_candidates(
        pd.DataFrame(rows),
        window_days=90,
        per_metric_by_unit={"hero": 2, "free": 3},
    )

    assert selected.groupby("analysis_unit").size().to_dict() == {
        "free": 9,
        "hero": 6,
    }
    assert set(selected.loc[selected["analysis_unit"] == "hero", "board_id"]) == {2294}
