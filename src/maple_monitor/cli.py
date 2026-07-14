import json

import typer
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from maple_monitor.db import create_engine_from_env
from maple_monitor.ops.health import database_health


app = typer.Typer(help="Operate the Maple Inven monitor.", invoke_without_command=True)


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
