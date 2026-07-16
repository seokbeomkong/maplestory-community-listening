from pathlib import Path

import yaml


def test_production_compose_uses_persistent_private_postgresql() -> None:
    compose = yaml.safe_load(Path("compose.prod.yaml").read_text(encoding="utf-8"))
    postgres = compose["services"]["postgres"]
    scheduler = compose["services"]["scheduler"]

    assert postgres["volumes"] == ["postgres_data:/var/lib/postgresql/data"]
    assert postgres["ports"] == ["127.0.0.1:${POSTGRES_HOST_PORT:-5432}:5432"]
    assert "tmpfs" not in postgres
    assert compose["volumes"] == {"postgres_data": {}}
    assert scheduler["restart"] == "unless-stopped"
    assert scheduler["command"] == [
        "maple-monitor",
        "scheduler",
        "--settings",
        "/app/config/settings.yaml",
    ]
    assert scheduler["healthcheck"]["test"] == [
        "CMD",
        "maple-monitor",
        "collector-health",
        "--max-age-hours",
        "13",
    ]
    assert scheduler["logging"]["options"] == {"max-size": "10m", "max-file": "5"}
    assert "maple_monitor_test" not in Path("compose.prod.yaml").read_text(encoding="utf-8")


def test_production_image_runs_as_a_non_root_user() -> None:
    dockerfile = Path("docker/Dockerfile").read_text(encoding="utf-8")

    assert "USER maple" in dockerfile
    assert "COPY --chown=maple:maple" in dockerfile


def test_production_image_installs_only_collector_dependencies() -> None:
    dockerfile = Path("docker/Dockerfile").read_text(encoding="utf-8")

    assert "uv sync --frozen --no-dev" in dockerfile
    assert "uv pip check" in dockerfile
    assert "streamlit" not in dockerfile.casefold()
    assert "pandas" not in dockerfile.casefold()
    assert "pyarrow" not in dockerfile.casefold()


def test_production_password_example_fails_closed() -> None:
    example = Path(".env.production.example").read_text(encoding="utf-8")

    assert "POSTGRES_PASSWORD=\n" in example
    assert "replace_with" not in example


def test_production_password_interpolation_rejects_blank_or_missing_values() -> None:
    compose = Path("compose.prod.yaml").read_text(encoding="utf-8")

    assert compose.count("${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD}") == 2
    assert "${POSTGRES_PASSWORD?Set POSTGRES_PASSWORD}" not in compose
