from __future__ import annotations

import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from maple_monitor.dashboard.export_data import ExportArchiveError, load_export_archive


_POSTS = (
    "board_id,board_name,post_id,analysis_unit,title,published_at,source_url,"
    "current_category,observed_at_slot_kst,observed_at_actual,views,recommendations,"
    "comments,config_version\n"
    "5974,자유 게시판,10,free,테스트 제목,2026-07-17 00:00:00+09,"
    "https://www.inven.co.kr/board/maple/5974/10,수다,2026-07-17 00:20:00+09,"
    "2026-07-17 00:20:03+09,120,4,7,abc\n"
)
_RANKINGS = (
    "analysis_unit,metric,as_of_slot_kst,rank,board_id,post_id,title,source_url,"
    "metric_value,config_version\n"
    "free,comments,2026-07-17 00:20:00+09,1,5974,10,테스트 제목,"
    "https://www.inven.co.kr/board/maple/5974/10,7,abc\n"
)
_RUNS = (
    "id,job_type,scheduled_at_slot_kst,status,config_version,started_at,finished_at,"
    "diagnostics\n"
    'run-1,metadata:free,2026-07-17 00:20:00+09,succeeded,abc,'
    '2026-07-17 00:20:00+09,2026-07-17 00:21:00+09,"{}"\n'
)
_QUARANTINE = (
    "id,source_kind,source_ref,content_hash,findings,risk_score,quarantined_at,"
    "review_state,reviewer,note,released_at\n"
)


def _write_export(
    path: Path,
    *,
    posts: str = _POSTS,
    omit: str | None = None,
    corrupt_checksum: bool = False,
) -> Path:
    members = {
        "latest_post_metrics.csv": posts,
        "cumulative_top50.csv": _RANKINGS,
        "collection_runs.csv": _RUNS,
        "security_quarantine.csv": _QUARANTINE,
    }
    encoded = {
        name: ("\ufeff" + body).encode("utf-8") for name, body in members.items() if name != omit
    }
    checksums = []
    for name, content in encoded.items():
        digest = hashlib.sha256(content).hexdigest()
        if corrupt_checksum and name == "latest_post_metrics.csv":
            digest = "0" * 64
        checksums.append(f"{digest}  {name}\n")

    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, content in encoded.items():
            archive.writestr(name, content)
        archive.writestr("SHA256SUMS.txt", "".join(checksums).encode("ascii"))
    return path


def test_load_export_archive_validates_and_types_all_tables(tmp_path: Path) -> None:
    bundle = load_export_archive(_write_export(tmp_path / "production.zip"))

    assert bundle.posts["views"].dtype.kind in "iu"
    assert bundle.posts["published_at"].dt.tz is not None
    assert bundle.posts.iloc[0]["title"] == "테스트 제목"
    assert bundle.checksums["latest_post_metrics.csv"] is True
    assert bundle.quarantine.empty


def test_load_export_archive_rejects_checksum_mismatch(tmp_path: Path) -> None:
    path = _write_export(tmp_path / "corrupt.zip", corrupt_checksum=True)

    with pytest.raises(ExportArchiveError, match="checksum"):
        load_export_archive(path)


def test_load_export_archive_rejects_missing_member(tmp_path: Path) -> None:
    path = _write_export(tmp_path / "missing.zip", omit="collection_runs.csv")

    with pytest.raises(ExportArchiveError, match="missing"):
        load_export_archive(path)


def test_load_export_archive_rejects_duplicate_post_identity(tmp_path: Path) -> None:
    duplicate_posts = _POSTS + _POSTS.split("\n", 1)[1]
    path = _write_export(tmp_path / "duplicate.zip", posts=duplicate_posts)

    with pytest.raises(ExportArchiveError, match="duplicate"):
        load_export_archive(path)


def test_load_export_archive_blanks_unapproved_source_links(tmp_path: Path) -> None:
    posts = _POSTS.replace("https://www.inven.co.kr/board/maple/5974/10", "https://evil.invalid/x")
    path = _write_export(tmp_path / "unsafe-url.zip", posts=posts)

    bundle = load_export_archive(path)

    assert bundle.posts.iloc[0]["source_url"] == ""
