from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from types import MappingProxyType
from typing import Final, Mapping
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile

import pandas as pd


class ExportArchiveError(ValueError):
    """Raised when a production export cannot be trusted for presentation."""


_SCHEMAS: Final = {
    "latest_post_metrics.csv": (
        "board_id",
        "board_name",
        "post_id",
        "analysis_unit",
        "title",
        "published_at",
        "source_url",
        "current_category",
        "observed_at_slot_kst",
        "observed_at_actual",
        "views",
        "recommendations",
        "comments",
        "config_version",
    ),
    "cumulative_top50.csv": (
        "analysis_unit",
        "metric",
        "as_of_slot_kst",
        "rank",
        "board_id",
        "post_id",
        "title",
        "source_url",
        "metric_value",
        "config_version",
    ),
    "collection_runs.csv": (
        "id",
        "job_type",
        "scheduled_at_slot_kst",
        "status",
        "config_version",
        "started_at",
        "finished_at",
        "diagnostics",
    ),
    "security_quarantine.csv": (
        "id",
        "source_kind",
        "source_ref",
        "content_hash",
        "findings",
        "risk_score",
        "quarantined_at",
        "review_state",
        "reviewer",
        "note",
        "released_at",
    ),
}
_REQUIRED_MEMBERS: Final = frozenset((*_SCHEMAS, "SHA256SUMS.txt"))
_DATETIME_COLUMNS: Final = {
    "latest_post_metrics.csv": ("published_at", "observed_at_slot_kst", "observed_at_actual"),
    "cumulative_top50.csv": ("as_of_slot_kst",),
    "collection_runs.csv": ("scheduled_at_slot_kst", "started_at", "finished_at"),
    "security_quarantine.csv": ("quarantined_at", "released_at"),
}
_INTEGER_COLUMNS: Final = {
    "latest_post_metrics.csv": (
        "board_id",
        "post_id",
        "views",
        "recommendations",
        "comments",
    ),
    "cumulative_top50.csv": ("rank", "board_id", "post_id", "metric_value"),
    "collection_runs.csv": (),
    "security_quarantine.csv": ("risk_score",),
}
_DUPLICATE_KEYS: Final = {
    "latest_post_metrics.csv": ("board_id", "post_id"),
    "cumulative_top50.csv": ("analysis_unit", "metric", "as_of_slot_kst", "rank"),
    "collection_runs.csv": ("id",),
    "security_quarantine.csv": ("id",),
}


@dataclass(frozen=True)
class ExportBundle:
    posts: pd.DataFrame
    rankings: pd.DataFrame
    runs: pd.DataFrame
    quarantine: pd.DataFrame
    checksums: Mapping[str, bool]
    source_path: Path


def _parse_checksum_manifest(content: bytes) -> dict[str, str]:
    expected: dict[str, str] = {}
    try:
        lines = content.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ExportArchiveError("checksum manifest is not ASCII") from exc
    for line in lines:
        parts = line.split()
        if len(parts) != 2 or len(parts[0]) != 64:
            raise ExportArchiveError("checksum manifest has an invalid entry")
        expected[parts[1].lstrip("*")] = parts[0].lower()
    return expected


def _verify_checksums(archive: ZipFile) -> Mapping[str, bool]:
    expected = _parse_checksum_manifest(archive.read("SHA256SUMS.txt"))
    csv_names = set(_SCHEMAS)
    if set(expected) != csv_names:
        raise ExportArchiveError("checksum manifest does not cover the required CSV files")
    results: dict[str, bool] = {}
    for name in sorted(csv_names):
        actual = hashlib.sha256(archive.read(name)).hexdigest()
        results[name] = actual == expected[name]
        if not results[name]:
            raise ExportArchiveError(f"checksum mismatch for {name}")
    return MappingProxyType(results)


def _approved_source_url(value: object) -> str:
    if not isinstance(value, str):
        return ""
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or parsed.hostname != "www.inven.co.kr":
        return ""
    return value.strip()


def _read_typed_csv(archive: ZipFile, name: str) -> pd.DataFrame:
    try:
        frame = pd.read_csv(BytesIO(archive.read(name)), encoding="utf-8-sig")
    except (UnicodeDecodeError, pd.errors.ParserError) as exc:
        raise ExportArchiveError(f"{name} is not a valid UTF-8 CSV") from exc
    required = list(_SCHEMAS[name])
    if frame.columns.tolist() != required:
        raise ExportArchiveError(f"{name} schema does not match the export contract")

    for column in _INTEGER_COLUMNS[name]:
        if frame.empty and column in frame:
            frame[column] = frame[column].astype("Int64")
            continue
        try:
            frame[column] = pd.to_numeric(frame[column], errors="raise").astype("int64")
        except (TypeError, ValueError) as exc:
            raise ExportArchiveError(f"{name}.{column} must contain integers") from exc

    for column in _DATETIME_COLUMNS[name]:
        if frame.empty or frame[column].isna().all():
            frame[column] = pd.to_datetime(frame[column], utc=True)
            continue
        try:
            frame[column] = pd.to_datetime(frame[column], errors="raise", utc=True)
        except (TypeError, ValueError) as exc:
            raise ExportArchiveError(f"{name}.{column} must contain timestamps") from exc

    keys = list(_DUPLICATE_KEYS[name])
    if not frame.empty and frame.duplicated(keys).any():
        raise ExportArchiveError(f"{name} contains duplicate rows at its expected grain")
    if "source_url" in frame:
        frame["source_url"] = frame["source_url"].map(_approved_source_url)
    return frame


def load_export_archive(path: Path) -> ExportBundle:
    """Load one checksum-verified production export into typed data frames."""

    if not isinstance(path, Path):
        raise TypeError("path must be a pathlib.Path")
    try:
        with ZipFile(path) as archive:
            members = {entry.filename for entry in archive.infolist() if not entry.is_dir()}
            missing = sorted(_REQUIRED_MEMBERS - members)
            if missing:
                raise ExportArchiveError(f"export archive is missing: {', '.join(missing)}")
            checksums = _verify_checksums(archive)
            posts = _read_typed_csv(archive, "latest_post_metrics.csv")
            rankings = _read_typed_csv(archive, "cumulative_top50.csv")
            runs = _read_typed_csv(archive, "collection_runs.csv")
            quarantine = _read_typed_csv(archive, "security_quarantine.csv")
    except (FileNotFoundError, IsADirectoryError, BadZipFile) as exc:
        raise ExportArchiveError("export archive could not be opened") from exc

    return ExportBundle(
        posts=posts,
        rankings=rankings,
        runs=runs,
        quarantine=quarantine,
        checksums=checksums,
        source_path=path.resolve(),
    )
