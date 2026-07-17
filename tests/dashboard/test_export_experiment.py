from __future__ import annotations

from maple_monitor.dashboard.export_experiment import experiment_blueprint


def test_experiment_blueprint_is_reproducible_and_does_not_invent_results() -> None:
    blueprint = experiment_blueprint()

    assert set(blueprint["intent_labels"]) == {
        "불만",
        "요구",
        "토론",
        "질문",
        "칭찬",
        "정보",
    }
    assert blueprint["sampling"]["strata"] == [
        "게시판",
        "직업",
        "게시 시기",
        "반응 백분위",
    ]
    assert "저반응 대조군" in blueprint["sampling"]["rule"]
    assert blueprint["evaluation"]["primary_metric"] == "macro-F1"
    assert "시간 순 분할" in blueprint["evaluation"]["splits"]
    assert "미관측 직업 분할" in blueprint["evaluation"]["splits"]
    assert blueprint["result_status"] == "본문·댓글 라벨 확보 후 실행"
    assert "score" not in blueprint
