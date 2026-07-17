from __future__ import annotations

from maple_monitor.local.opinion import analyze_post, classify_text, load_analysis_rules


def test_rule_model_labels_korean_request_and_negative_sentiment() -> None:
    rules = load_analysis_rules()

    label = classify_text("스킬 밸런스가 최악이라 반드시 개선해 주세요", rules)

    assert label.sentiment == "negative"
    assert label.intent == "request"
    assert label.topic == "밸런스·스킬"
    assert "최악" in label.evidence_terms


def test_post_body_and_comment_reaction_are_independent() -> None:
    rules = load_analysis_rules()

    label = analyze_post("밸런스가 최악이라 개선이 필요합니다", ["좋아요", "기대됩니다"], rules)

    assert label.body_sentiment == "negative"
    assert label.comment_reaction == "positive"
    assert label.model_version == "domain-lexicon-v1.1"


def test_title_contributes_to_topic_and_intent_but_not_body_sentiment() -> None:
    rules = load_analysis_rules()

    label = analyze_post(
        "현재 구조를 살펴봅니다",
        (),
        rules,
        title="보스 극딜 구조를 어떻게 생각하시나요 토론",
    )

    assert label.topic == "보스·전투"
    assert label.intent == "debate"
    assert label.body_sentiment == "neutral"
