from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from maple_monitor.dashboard.export_data import load_export_archive
from maple_monitor.local.artifacts import analysis_directory, archive_sha256, load_analysis_artifact
from maple_monitor.local.detail_client import DetailClient, RawDetail
from maple_monitor.local.detail_parser import (
    candidate_limits,
    load_selection_policy,
    parse_article,
    parse_comments,
    select_detail_candidates,
)
from maple_monitor.local.opinion import AnalysisRules, analyze_post, load_analysis_rules
from maple_monitor.security.scanner import scan_untrusted


@dataclass(frozen=True)
class RefreshSummary:
    fetched_posts: int
    analyzed_posts: int
    analyzed_comments: int
    quarantined_items: int
    failed_posts: int
    artifact_path: str


def _write_atomic(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    os.replace(temporary, path)


def _relabel_cached_rows(
    posts: pd.DataFrame,
    comments: pd.DataFrame,
    *,
    rules: AnalysisRules,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if posts.empty:
        return posts, comments
    updated_posts = posts.copy()
    updated_comments = comments.copy()
    for column in (
        "body_sentiment",
        "comment_reaction",
        "intent",
        "topic",
        "evidence_terms",
        "model_version",
    ):
        updated_posts[column] = updated_posts[column].astype("object")
    if not updated_comments.empty:
        updated_comments["sentiment"] = [
            analyze_post(str(text), (), rules).body_sentiment
            for text in updated_comments["text"]
        ]
        updated_comments["model_version"] = rules.version
        comment_groups = (
            updated_comments.groupby(["board_id", "post_id"])["text"]
            .apply(lambda values: [str(value) for value in values])
            .to_dict()
        )
    else:
        comment_groups = {}
    for index, row in updated_posts.iterrows():
        key = (row["board_id"], row["post_id"])
        label = analyze_post(
            str(row.get("body_excerpt", "")),
            comment_groups.get(key, ()),
            rules,
            title=str(row.get("title", "")),
        )
        updated_posts.loc[index, "body_sentiment"] = label.body_sentiment
        updated_posts.loc[index, "comment_reaction"] = label.comment_reaction
        updated_posts.loc[index, "intent"] = label.intent
        updated_posts.loc[index, "topic"] = label.topic
        updated_posts.loc[index, "confidence"] = label.confidence
        updated_posts.loc[index, "evidence_terms"] = " · ".join(
            label.evidence_terms
        )
        updated_posts.loc[index, "model_version"] = label.model_version
    return updated_posts, updated_comments


def refresh_analysis(
    export_path: Path,
    analysis_root: Path,
    *,
    fetcher: Callable[[int, int], RawDetail] | None = None,
) -> RefreshSummary:
    export_path = export_path.resolve()
    analysis_root = analysis_root.resolve()
    target = analysis_directory(export_path, analysis_root)
    existing = load_analysis_artifact(export_path, analysis_root)
    bundle = load_export_archive(export_path)
    rules = load_analysis_rules()
    policy = load_selection_policy()
    candidates = select_detail_candidates(
        bundle.posts,
        window_days=int(policy["window_days"]),
        per_metric_by_unit=candidate_limits(bundle.posts, policy),
    )
    if (
        existing is not None
        and bool(existing.manifest.get("complete"))
        and existing.manifest.get("selection_policy") == policy
        and existing.manifest.get("model_version") == rules.version
    ):
        return RefreshSummary(
            0, len(existing.posts), len(existing.comments), 0, 0, str(target)
        )

    candidate_keys = set(
        candidates[["board_id", "post_id"]].itertuples(index=False, name=None)
    )
    reused_posts = pd.DataFrame()
    reused_comments = pd.DataFrame()
    if existing is not None:
        existing_keys = list(
            existing.posts[["board_id", "post_id"]].itertuples(index=False, name=None)
        )
        keep_mask = [key in candidate_keys for key in existing_keys]
        reused_posts = existing.posts.loc[keep_mask].copy()
        reused_keys = set(
            reused_posts[["board_id", "post_id"]].itertuples(index=False, name=None)
        )
        if not existing.comments.empty:
            comment_keys = list(
                existing.comments[["board_id", "post_id"]].itertuples(
                    index=False, name=None
                )
            )
            reused_comments = existing.comments.loc[
                [key in reused_keys for key in comment_keys]
            ].copy()
    else:
        reused_keys = set()

    reused_posts, reused_comments = _relabel_cached_rows(
        reused_posts,
        reused_comments,
        rules=rules,
    )

    missing = candidates.loc[
        [
            (row.board_id, row.post_id) not in reused_keys
            for row in candidates.itertuples(index=False)
        ]
    ]
    post_rows: list[dict[str, object]] = reused_posts.to_dict("records")
    comment_rows: list[dict[str, object]] = reused_comments.to_dict("records")
    quarantined = 0
    failures = 0

    client: DetailClient | None = None
    if fetcher is None:
        client = DetailClient()
        client.__enter__()
        fetcher = client.fetch
    try:
        for row in missing.itertuples(index=False):
            try:
                raw = fetcher(int(row.board_id), int(row.post_id))
                article = parse_article(raw.article)
                parsed_comments = parse_comments(raw.comments)
                body_scan = scan_untrusted(article.body, "body")
                if body_scan.quarantined(70):
                    quarantined += 1
                    continue
                safe_comments: list[str] = []
                safe_comment_records = []
                for comment in parsed_comments.comments:
                    scan = scan_untrusted(comment.text, "comment")
                    if scan.quarantined(70):
                        quarantined += 1
                        continue
                    safe_comments.append(scan.normalized_text)
                    safe_comment_records.append((comment, scan.normalized_text))
                label = analyze_post(
                    body_scan.normalized_text,
                    safe_comments,
                    rules,
                    title=str(row.title),
                )
                post_rows.append(
                    {
                        "board_id": int(row.board_id),
                        "post_id": int(row.post_id),
                        "analysis_unit": row.analysis_unit,
                        "title": row.title,
                        "published_at": row.published_at,
                        "source_url": row.source_url,
                        "selection_reason": row.selection_reason,
                        "views": int(row.views),
                        "recommendations": int(row.recommendations),
                        "comment_count": int(row.comments),
                        "analyzed_comment_count": len(safe_comments),
                        "comments_complete": parsed_comments.complete,
                        "body_sentiment": label.body_sentiment,
                        "comment_reaction": label.comment_reaction,
                        "intent": label.intent,
                        "topic": label.topic,
                        "confidence": label.confidence,
                        "evidence_terms": " · ".join(label.evidence_terms),
                        "body_excerpt": body_scan.normalized_text[:500],
                        "model_version": label.model_version,
                    }
                )
                for comment, normalized in safe_comment_records:
                    comment_rows.append(
                        {
                            "board_id": int(row.board_id),
                            "post_id": int(row.post_id),
                            "comment_id": comment.comment_id,
                            "parent_id": comment.parent_id,
                            "published_at": comment.published_at,
                            "text": normalized[:500],
                            "sentiment": analyze_post(normalized, (), rules).body_sentiment,
                            "model_version": rules.version,
                        }
                    )
            except Exception:
                failures += 1
    finally:
        if client is not None:
            client.__exit__(None, None, None)

    target.mkdir(parents=True, exist_ok=True)
    posts = pd.DataFrame.from_records(post_rows)
    comments = pd.DataFrame.from_records(comment_rows)
    _write_atomic(posts, target / "semantic_posts.csv")
    _write_atomic(comments, target / "semantic_comments.csv")
    now = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    manifest = {
        "schema_version": 1,
        "complete": True,
        "source_archive": export_path.name,
        "source_sha256": archive_sha256(export_path),
        "model_version": rules.version,
        "selection_policy": policy,
        "generated_at_kst": now,
        "selected_posts": len(candidates),
        "analyzed_posts": len(posts),
        "analyzed_comments": len(comments),
        "quarantined_items": quarantined,
        "failed_posts": failures,
        "refresh_policy": "6시간 수집 후 증분 분석 · 모델 재학습 월 1회 또는 드리프트 발생 시",
    }
    temporary_manifest = target / "manifest.json.tmp"
    temporary_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary_manifest, target / "manifest.json")
    return RefreshSummary(
        fetched_posts=len(missing),
        analyzed_posts=len(posts),
        analyzed_comments=len(comments),
        quarantined_items=quarantined,
        failed_posts=failures,
        artifact_path=str(target),
    )
