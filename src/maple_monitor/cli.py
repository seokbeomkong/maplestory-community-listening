import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

import typer
import yaml
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from maple_monitor.collection.client import ListPageClientError, fetch_list_page
from maple_monitor.collection.parser import InvalidSourcePage, parse_list_page
from maple_monitor.collection.repository import SnapshotConfigConflict
from maple_monitor.collection.service import align_kst_slot, collect_board_slot
from maple_monitor.config import LoadedSettings, load_settings
from maple_monitor.db import create_engine_from_env
from maple_monitor.db import session_scope
from maple_monitor.ops.health import database_health
from maple_monitor.ops.scheduler import (
    collect_and_rank_with_retries,
    collector_health,
    run_scheduler,
    summary_payload,
)


app = typer.Typer(help="Operate the Maple Inven monitor.", invoke_without_command=True)
KST: Final = ZoneInfo("Asia/Seoul")


@app.callback()
def main() -> None:
    """Run Maple Inven monitor operator commands."""


@app.command()
def health() -> None:
    """Check whether the PostgreSQL database is reachable."""
    engine: Engine | None = None
    try:
        engine = create_engine_from_env()
        result = database_health(engine)
    except (KeyError, SQLAlchemyError):
        result = {"database": "error"}
    finally:
        if engine is not None:
            engine.dispose()

    typer.echo(json.dumps(result, sort_keys=True))
    if result["database"] != "ok":
        raise typer.Exit(code=1)


def _parse_board(value: str) -> int:
    if re.fullmatch(r"[0-9]{1,10}", value) is None:
        raise ValueError("board must be a numeric identifier")
    board_id = int(value)
    if board_id != 2294:
        raise ValueError("unsupported board")
    return board_id


def _parse_exact_slot(value: str, loaded_settings: LoadedSettings) -> datetime:
    try:
        supplied = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("collection time must be ISO-8601") from None
    if supplied.tzinfo is None or supplied.utcoffset() is None:
        raise ValueError("collection time must be timezone-aware")
    collection = loaded_settings.settings.collection
    aligned = align_kst_slot(
        supplied,
        interval_hours=collection.interval_hours,
        minute=collection.slot_minute_kst,
    )
    if supplied != aligned:
        raise ValueError("collection time must be an exact aligned KST slot")
    return aligned


def _current_kst_time() -> datetime:
    return datetime.now(KST)


@app.command("collect-metadata")
def collect_metadata(
    board: str = typer.Option(..., "--board", help="Public board identifier."),
    at: str = typer.Option(..., "--at", help="Exact timezone-aware collection slot."),
    settings: Path = typer.Option(
        Path("config/settings.yaml"),
        "--settings",
        help="Validated monitor settings file.",
    ),
) -> None:
    """Collect one bounded metadata list into its aligned snapshot."""

    engine: Engine | None = None
    try:
        loaded_settings = load_settings(settings)
        board_id = _parse_board(board)
        slot = _parse_exact_slot(at, loaded_settings)
        html = fetch_list_page(board_id)
        fetched_at = _current_kst_time()
        items = parse_list_page(board_id, html, fetched_at)
        engine = create_engine_from_env()
        with session_scope(engine) as session:
            summary = collect_board_slot(
                session,
                board_id,
                items,
                slot,
                loaded_settings,
                fetched_at=fetched_at,
            )
    except (
        InvalidSourcePage,
        KeyError,
        ListPageClientError,
        OSError,
        SnapshotConfigConflict,
        SQLAlchemyError,
        TypeError,
        ValidationError,
        ValueError,
        yaml.YAMLError,
    ):
        typer.echo(json.dumps({"error": "collection_failed"}, sort_keys=True))
        raise typer.Exit(code=1) from None
    finally:
        if engine is not None:
            engine.dispose()

    typer.echo(json.dumps(asdict(summary), sort_keys=True))


@app.command("collect-and-rank")
def collect_and_rank(
    now: bool = typer.Option(False, "--now", help="Collect the latest aligned slot."),
    settings: Path = typer.Option(
        Path("config/settings.yaml"),
        "--settings",
        help="Validated monitor settings file.",
    ),
) -> None:
    """Collect live metadata and refresh cumulative ranks in one transaction."""

    if not now:
        typer.echo(json.dumps({"error": "collection_failed"}, sort_keys=True))
        raise typer.Exit(code=1)
    try:
        summary = collect_and_rank_with_retries(settings)
    except Exception:
        typer.echo(json.dumps({"error": "collection_failed"}, sort_keys=True))
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(summary_payload(summary), sort_keys=True))


@app.command("scheduler")
def scheduler_command(
    settings: Path = typer.Option(
        Path("config/settings.yaml"),
        "--settings",
        help="Validated monitor settings file.",
    ),
) -> None:
    """Continuously run the production metadata collector on KST boundaries."""

    try:
        run_scheduler(settings)
    except Exception:
        typer.echo(json.dumps({"error": "scheduler_failed"}, sort_keys=True))
        raise typer.Exit(code=1) from None


@app.command("collector-health")
def collector_health_command(
    max_age_hours: int = typer.Option(
        13,
        "--max-age-hours",
        min=1,
        max=168,
        help="Maximum allowed age of the last successful collection.",
    ),
) -> None:
    """Fail when the production collector has no recent successful run."""

    try:
        healthy = collector_health(max_age_hours)
    except Exception:
        healthy = False
    typer.echo(json.dumps({"collector": "ok" if healthy else "stale"}, sort_keys=True))
    if not healthy:
        raise typer.Exit(code=1)
