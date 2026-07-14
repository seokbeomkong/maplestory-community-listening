from typer.testing import CliRunner

from maple_monitor.cli import app


def test_cli_help_is_available() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0, str(result.exception)
    assert "Operate the Maple Inven monitor" in result.output
