from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class AnalysisArtifact:
    manifest: Mapping[str, object]
    posts: pd.DataFrame
    comments: pd.DataFrame


def archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analysis_directory(export_path: Path, root: Path) -> Path:
    return root / export_path.stem


def resolve_production_export(path_value: str | Path) -> Path:
    path = Path(path_value)
    if path.is_dir():
        candidates = sorted(path.glob("production-*.zip"), key=lambda item: item.name)
        if not candidates:
            raise FileNotFoundError("production export ZIP was not found")
        return candidates[-1]
    return path


def load_analysis_artifact(export_path: Path, root: Path) -> AnalysisArtifact | None:
    target = analysis_directory(export_path, root)
    try:
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 1:
            return None
        if manifest.get("source_sha256") != archive_sha256(export_path):
            return None
        posts = pd.read_csv(target / "semantic_posts.csv", encoding="utf-8-sig")
        comments = pd.read_csv(target / "semantic_comments.csv", encoding="utf-8-sig")
    except (OSError, ValueError, pd.errors.ParserError):
        return None
    return AnalysisArtifact(manifest=manifest, posts=posts, comments=comments)
