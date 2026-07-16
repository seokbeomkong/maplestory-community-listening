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


def test_operations_guide_covers_multi_source_collection_and_acceptance() -> None:
    guide = " ".join(
        Path("docs/operations/vps-production.md")
        .read_text(encoding="utf-8")
        .casefold()
        .split()
    )

    for source in (
        "warrior (2294)",
        "magician (2295)",
        "archer (2296)",
        "thief (2297)",
        "pirate (2298)",
        "free (5974)",
        "q&a (2300)",
        "tips (2304)",
    ):
        assert source in guide

    assert "incremental_min_pages=2" in guide
    assert "incremental_overlap_pages=1" in guide
    assert "incremental_max_pages=100" in guide
    assert "prior high-water boundary" in guide
    assert "one overlap page" in guide
    assert "40-page" in guide
    assert "durable per aligned slot" in guide
    assert "90-day" in guide
    assert "partial" in guide
    assert "collection_runs.csv" in guide
    assert "diagnostics" in guide
    assert "metadata:<source_key>" in guide
    assert "metadata-backfill" in guide
    assert "group by b.id,b.name order by b.id" in guide
    assert "run --rm migrate" in guide
    assert "up -d --build scheduler" in guide
    assert "maple-monitor collect-and-rank --now" in guide
    assert "eight board rows" in guide
    assert "only board 2294" not in guide
    assert "hero board every six hours" not in guide
