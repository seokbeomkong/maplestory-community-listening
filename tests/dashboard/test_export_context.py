from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from maple_monitor.dashboard.export_context import export_signature, resolve_export_path
from maple_monitor.local.artifacts import analysis_directory, archive_sha256, load_analysis_artifact
from maple_monitor.local.detail_client import RawDetail
from maple_monitor.local.opinion import load_analysis_rules
from maple_monitor.local.pipeline import refresh_analysis


def test_export_directory_resolves_latest_production_archive(
    tmp_path: Path, export_zip: Path
) -> None:
    older = tmp_path / "production-20260716-190257.zip"
    latest = tmp_path / "production-20260717-090000.zip"
    older.write_bytes(export_zip.read_bytes())
    latest.write_bytes(export_zip.read_bytes())

    assert resolve_export_path(tmp_path) == latest
    assert export_signature(tmp_path)[0] == str(latest.resolve())


def test_export_path_still_accepts_one_explicit_archive(export_zip: Path) -> None:
    assert resolve_export_path(export_zip) == export_zip


def test_export_directory_without_release_fails_closed(tmp_path: Path) -> None:
    (tmp_path / ".production-20260717.partial.zip").write_bytes(b"partial")

    with pytest.raises(FileNotFoundError, match="production"):
        resolve_export_path(tmp_path)


def test_analysis_artifact_requires_matching_archive_digest(
    export_zip: Path, tmp_path: Path
) -> None:
    target = analysis_directory(export_zip, tmp_path)
    target.mkdir(parents=True)
    (target / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "source_sha256": "0" * 64}), encoding="utf-8"
    )
    pd.DataFrame().to_csv(target / "semantic_posts.csv", index=False)
    pd.DataFrame().to_csv(target / "semantic_comments.csv", index=False)

    assert load_analysis_artifact(export_zip, tmp_path) is None
    assert archive_sha256(export_zip) != "0" * 64


def test_analysis_refresh_writes_and_reuses_complete_artifact(
    export_zip: Path, tmp_path: Path
) -> None:
    calls: list[tuple[int, int]] = []

    def fetcher(board_id: int, post_id: int) -> RawDetail:
        calls.append((board_id, post_id))
        article = (
            '<html><div id="powerbbsContent">스킬 밸런스 개선이 필요합니다</div></html>'
        ).encode()
        comments = json.dumps(
            {
                "message": 1,
                "cmtcount": 1,
                "commentlist": [
                    {
                        "list": [
                            {
                                "__attr__": {"cmtidx": post_id, "cmtpidx": post_id},
                                "o_date": "2026-07-17 01:00:00",
                                "o_comment": "좋아요 기대됩니다",
                            }
                        ]
                    }
                ],
            },
            ensure_ascii=False,
        ).encode()
        return RawDetail(article=article, comments=comments)

    first = refresh_analysis(export_zip, tmp_path, fetcher=fetcher)
    second = refresh_analysis(export_zip, tmp_path, fetcher=fetcher)
    artifact = load_analysis_artifact(export_zip, tmp_path)

    assert first.fetched_posts == 4
    assert second.fetched_posts == 0
    assert len(calls) == 4
    assert artifact is not None
    assert len(artifact.posts) == 4
    assert len(artifact.comments) == 4

    target = Path(first.artifact_path)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["selection_policy"]["version"] == "engagement-top-v2"
    manifest["selection_policy"] = {"version": "engagement-top-v1"}
    manifest["model_version"] = "legacy-model"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    reduced_posts = artifact.posts.iloc[:-1].copy()
    removed = artifact.posts.iloc[-1]
    reduced_comments = artifact.comments.loc[
        ~(
            (artifact.comments["board_id"] == removed["board_id"])
            & (artifact.comments["post_id"] == removed["post_id"])
        )
    ].copy()
    reduced_posts.to_csv(target / "semantic_posts.csv", index=False, encoding="utf-8-sig")
    reduced_comments.to_csv(target / "semantic_comments.csv", index=False, encoding="utf-8-sig")

    expanded = refresh_analysis(export_zip, tmp_path, fetcher=fetcher)

    assert expanded.fetched_posts == 1
    assert len(calls) == 5
    expanded_artifact = load_analysis_artifact(export_zip, tmp_path)
    assert expanded_artifact is not None
    assert len(expanded_artifact.posts) == 4
    assert set(expanded_artifact.posts["model_version"]) == {load_analysis_rules().version}
