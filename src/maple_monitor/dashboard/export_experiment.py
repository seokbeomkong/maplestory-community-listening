from __future__ import annotations

from typing import Any


def experiment_blueprint() -> dict[str, Any]:
    """Return the planned, not-yet-executed semantic-analysis protocol."""

    return {
        "intent_labels": ["불만", "요구", "토론", "질문", "칭찬", "정보"],
        "topic_labels": [
            "스킬·구조",
            "밸런스",
            "사냥",
            "보스",
            "장비·성장",
            "경제",
            "운영·이벤트",
            "커뮤니티",
        ],
        "sampling": {
            "strata": ["게시판", "직업", "게시 시기", "반응 백분위"],
            "unit": "게시물 본문과 댓글 묶음",
            "seed": 20260717,
            "rule": "각 층에서 무작위 추출하고 저반응 대조군과 고반응 표본을 함께 보강",
        },
        "label_quality": {
            "gold_set": "이중 라벨링 후 불일치 합의",
            "agreement": "Krippendorff's alpha와 라벨별 혼동표",
            "guide": "경계 사례와 복수 의도 우선순위를 버전 관리",
        },
        "models": [
            "TF-IDF + 선형 분류기 기준선",
            "한국어 소형 언어모델 미세조정",
        ],
        "evaluation": {
            "primary_metric": "macro-F1",
            "secondary_metrics": ["라벨별 F1", "확률 보정", "오류 유형별 빈도"],
            "splits": ["시간 순 분할", "미관측 직업 분할"],
        },
        "result_status": "본문·댓글 라벨 확보 후 실행",
    }
