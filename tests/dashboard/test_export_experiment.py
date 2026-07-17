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
    assert {item["board"] for item in blueprint["applications"]} == {
        "직업 게시판",
        "자유게시판",
        "질문과 답변",
        "팁과 노하우",
    }
    assert blueprint["language_model_roles"] == [
        "라벨링 보조",
        "지도학습 분류",
        "근거 기반 요약",
        "오류 분석",
    ]
    assert [item["modality"] for item in blueprint["modalities"]] == [
        "텍스트",
        "반응·시간",
        "게시판·직업",
        "첨부 이미지",
    ]
    assert blueprint["multimodal_model"]["fusion"] == "late fusion 기준선 → cross-attention"
    assert blueprint["evaluation"]["ablations"] == [
        "텍스트만",
        "텍스트+메타데이터",
        "텍스트+메타데이터+이미지",
    ]
    assert "자동 제재" in blueprint["decision_boundary"]
    assert blueprint["production_pipeline"] == [
        "검증 ZIP 감지",
        "특징·배치 추론",
        "릴리스·모델 버전 결과 저장",
        "대시보드 갱신",
        "드리프트 감시",
    ]
    assert "재학습하지 않음" in blueprint["retraining_policy"]
    assert "score" not in blueprint
