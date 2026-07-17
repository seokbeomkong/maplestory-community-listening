from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Sequence

import yaml


Sentiment = Literal["positive", "neutral", "negative", "mixed"]


@dataclass(frozen=True)
class AnalysisRules:
    version: str
    positive: tuple[str, ...]
    negative: tuple[str, ...]
    intents: Mapping[str, tuple[str, ...]]
    topics: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class TextLabel:
    sentiment: Sentiment
    intent: str
    topic: str
    confidence: float
    evidence_terms: tuple[str, ...]


@dataclass(frozen=True)
class PostLabel:
    body_sentiment: Sentiment
    comment_reaction: Sentiment
    intent: str
    topic: str
    confidence: float
    evidence_terms: tuple[str, ...]
    model_version: str


def load_analysis_rules(path: Path | None = None) -> AnalysisRules:
    rules_path = path or Path(__file__).parents[3] / "config" / "analysis_rules.yaml"
    payload = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    return AnalysisRules(
        version=str(payload["version"]),
        positive=tuple(payload["sentiment"]["positive"]),
        negative=tuple(payload["sentiment"]["negative"]),
        intents={key: tuple(value) for key, value in payload["intent"].items()},
        topics={key: tuple(value) for key, value in payload["topic"].items()},
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).casefold().strip()


def _matches(text: str, terms: Sequence[str]) -> list[str]:
    return [term for term in terms if _normalize(term) in text]


def _strongest(text: str, groups: Mapping[str, tuple[str, ...]], default: str) -> str:
    scores = [(len(_matches(text, terms)), -index, label) for index, (label, terms) in enumerate(groups.items())]
    score, _, label = max(scores, default=(0, 0, default))
    return label if score else default


def classify_text(text: str, rules: AnalysisRules) -> TextLabel:
    normalized = _normalize(text)
    positive = _matches(normalized, rules.positive)
    negative = _matches(normalized, rules.negative)
    if positive and negative:
        sentiment: Sentiment = "mixed"
    elif positive:
        sentiment = "positive"
    elif negative:
        sentiment = "negative"
    else:
        sentiment = "neutral"
    evidence = tuple(dict.fromkeys([*positive, *negative]))[:5]
    hits = len(positive) + len(negative)
    confidence = min(0.95, 0.45 + 0.15 * hits) if hits else 0.35
    return TextLabel(
        sentiment=sentiment,
        intent=_strongest(normalized, rules.intents, "information"),
        topic=_strongest(normalized, rules.topics, "커뮤니티"),
        confidence=confidence,
        evidence_terms=evidence,
    )


def analyze_post(
    body: str,
    comments: Sequence[str],
    rules: AnalysisRules,
    *,
    title: str = "",
) -> PostLabel:
    body_label = classify_text(body, rules)
    context_label = classify_text(f"{title} {body}", rules)
    reactions = [classify_text(comment, rules).sentiment for comment in comments]
    non_neutral = [value for value in reactions if value != "neutral"]
    if not non_neutral:
        reaction: Sentiment = "neutral"
    else:
        counts = Counter(non_neutral)
        leaders = [label for label, count in counts.items() if count == max(counts.values())]
        reaction = leaders[0] if len(leaders) == 1 else "mixed"
    return PostLabel(
        body_sentiment=body_label.sentiment,
        comment_reaction=reaction,
        intent=context_label.intent,
        topic=context_label.topic,
        confidence=body_label.confidence,
        evidence_terms=body_label.evidence_terms,
        model_version=rules.version,
    )
