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
        "applications": [
            {
                "board": "직업 게시판",
                "purpose": "불만·요구·토론과 직업별 이슈 구조화",
                "input": "제목·본문·댓글",
                "output": "의도, 이슈, 근거 문장",
            },
            {
                "board": "자유게시판",
                "purpose": "전체 커뮤니티의 신규 이슈와 반응 흐름 탐지",
                "input": "대화 묶음·게시 시각·반응",
                "output": "주제 추세, 입장 분포, 근거 게시물",
            },
            {
                "board": "질문과 답변",
                "purpose": "질문 유형과 답변 정보의 연결 구조 파악",
                "input": "질문 본문·댓글",
                "output": "질문 주제, 답변 유형, 추가 정보 필요 여부",
            },
            {
                "board": "팁과 노하우",
                "purpose": "재사용 가능한 공략·정보 체계 구축",
                "input": "본문·첨부 이미지·댓글",
                "output": "정보 분류, 대상 콘텐츠, 근거 요약",
            },
        ],
        "language_model_roles": [
            "라벨링 보조",
            "지도학습 분류",
            "근거 기반 요약",
            "오류 분석",
        ],
        "modalities": [
            {
                "modality": "텍스트",
                "features": "제목·본문·댓글·OCR 텍스트",
                "status": "본문·댓글 추가 수집 필요",
            },
            {
                "modality": "반응·시간",
                "features": "조회·추천·댓글·게시/관측 시각",
                "status": "현재 보유",
            },
            {
                "modality": "게시판·직업",
                "features": "게시판 목적·직업·분석 단위",
                "status": "현재 보유",
            },
            {
                "modality": "첨부 이미지",
                "features": "스킬 UI·장비·오류 화면·공략 이미지",
                "status": "추가 수집 및 권리 검토 필요",
            },
        ],
        "multimodal_model": {
            "text_branch": "한국어 인코더 또는 소형 언어모델",
            "metadata_branch": "수치 정규화 + 범주 임베딩",
            "image_branch": "OCR + 비전 인코더(이미지 표본이 있을 때)",
            "fusion": "late fusion 기준선 → cross-attention",
            "outputs": ["대화 의도", "이슈 주제", "댓글 입장", "근거 문장"],
        },
        "evaluation": {
            "primary_metric": "macro-F1",
            "secondary_metrics": ["라벨별 F1", "확률 보정", "오류 유형별 빈도"],
            "splits": ["시간 순 분할", "미관측 직업 분할"],
            "ablations": [
                "텍스트만",
                "텍스트+메타데이터",
                "텍스트+메타데이터+이미지",
            ],
        },
        "decision_boundary": (
            "모델 결과는 이슈 탐색과 표본 우선순위에만 사용하며 자동 제재, "
            "개인 평가, 조회·추천 기반 감성 판정에는 사용하지 않음"
        ),
        "production_pipeline": [
            "검증 ZIP 감지",
            "특징·배치 추론",
            "릴리스·모델 버전 결과 저장",
            "대시보드 갱신",
            "드리프트 감시",
        ],
        "retraining_policy": (
            "새 ZIP마다 재학습하지 않음. 라벨 체계 변경, 충분한 신규 골드 데이터, "
            "일반화 성능 또는 보정 드리프트가 확인될 때만 재학습"
        ),
        "result_status": "본문·댓글 라벨 확보 후 실행",
    }
