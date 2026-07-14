import typer


app = typer.Typer(help="Operate the Maple Inven monitor.", invoke_without_command=True)


@app.callback()
def main() -> None:
    """Run Maple Inven monitor operator commands."""
