from __future__ import annotations

import html as html_lib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml
from bs4 import BeautifulSoup


class DetailParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedArticle:
    body: str


@dataclass(frozen=True)
class ParsedComment:
    comment_id: int
    parent_id: int
    published_at: str
    text: str


@dataclass(frozen=True)
class ParsedComments:
    reported_count: int
    comments: tuple[ParsedComment, ...]
    complete: bool


GENERAL_ANALYSIS_UNITS = frozenset({"free", "qna", "tips"})


def _plain_text(value: str) -> str:
    decoded = html_lib.unescape(html_lib.unescape(value)).replace("\xa0", " ")
    text = BeautifulSoup(decoded, "lxml").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def parse_article(content: bytes) -> ParsedArticle:
    soup = BeautifulSoup(content, "lxml")
    body = soup.select_one("#powerbbsContent")
    if body is None:
        raise DetailParseError("article body is missing")
    return ParsedArticle(body=_plain_text(str(body)))


def parse_comments(content: bytes) -> ParsedComments:
    try:
        payload = json.loads(content.decode("utf-8"))
        reported = int(payload["cmtcount"])
        groups = payload.get("commentlist", [])
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise DetailParseError("comment payload is invalid") from exc
    comments: list[ParsedComment] = []
    seen: set[int] = set()
    for group in groups:
        for item in group.get("list", []):
            attributes = item.get("__attr__", {})
            try:
                comment_id = int(attributes["cmtidx"])
                parent_id = int(attributes.get("cmtpidx", comment_id))
            except (KeyError, TypeError, ValueError):
                continue
            text = _plain_text(str(item.get("o_comment", "")))
            if not text or comment_id in seen:
                continue
            seen.add(comment_id)
            comments.append(
                ParsedComment(comment_id, parent_id, str(item.get("o_date", "")), text)
            )
    return ParsedComments(reported, tuple(comments), len(comments) == reported)


def load_selection_policy(path: Path | None = None) -> dict[str, int | str]:
    rules_path = path or Path(__file__).parents[3] / "config" / "analysis_rules.yaml"
    payload = yaml.safe_load(rules_path.read_text(encoding="utf-8"))["selection"]
    return {
        "version": str(payload["version"]),
        "window_days": int(payload["window_days"]),
        "job_per_metric": int(payload["job_per_metric"]),
        "general_per_metric": int(payload["general_per_metric"]),
    }


def candidate_limits(
    posts: pd.DataFrame, policy: Mapping[str, int | str]
) -> dict[str, int]:
    return {
        str(unit): int(
            policy[
                "general_per_metric"
                if str(unit) in GENERAL_ANALYSIS_UNITS
                else "job_per_metric"
            ]
        )
        for unit in posts["analysis_unit"].dropna().unique()
    }


def select_detail_candidates(
    posts: pd.DataFrame,
    *,
    window_days: int = 90,
    per_metric: int = 1,
    per_metric_by_unit: Mapping[str, int] | None = None,
) -> pd.DataFrame:
    if posts.empty:
        return posts.assign(selection_reason=pd.Series(dtype="string"))
    end = pd.to_datetime(posts["published_at"], utc=True).max()
    eligible = posts.loc[
        pd.to_datetime(posts["published_at"], utc=True)
        >= end - pd.Timedelta(int(window_days), unit="D")
    ]
    selected: list[pd.DataFrame] = []
    for metric in ("comments", "recommendations", "views"):
        ranked = eligible.sort_values(
            ["analysis_unit", metric, "published_at", "post_id"],
            ascending=[True, False, False, False],
        )
        for unit, rows in ranked.groupby("analysis_unit", sort=True):
            limit = (
                per_metric_by_unit.get(str(unit), per_metric)
                if per_metric_by_unit is not None
                else per_metric
            )
            selected.append(rows.head(int(limit)).assign(selection_reason=metric))
    return (
        pd.concat(selected, ignore_index=True)
        .drop_duplicates(["board_id", "post_id"], keep="first")
        .sort_values(["analysis_unit", "selection_reason", "post_id"])
        .reset_index(drop=True)
    )
