from __future__ import annotations

import os
from collections.abc import Callable
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool, text

from maple_monitor.models import Base


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"].replace("%", "%%"))
target_metadata = Base.metadata
_SNAPSHOT_PARENT_SCHEMA = "public"
_SNAPSHOT_PARENT_TABLE = "post_metric_snapshots"


def snapshot_partition_names(connection: Connection) -> frozenset[tuple[str, str]]:
    rows = connection.execute(
        text(
            """
            SELECT child_namespace.nspname AS child_schema, child.relname AS child_name
            FROM pg_catalog.pg_inherits AS inheritance
            JOIN pg_catalog.pg_class AS parent ON parent.oid = inheritance.inhparent
            JOIN pg_catalog.pg_namespace AS parent_namespace
              ON parent_namespace.oid = parent.relnamespace
            JOIN pg_catalog.pg_class AS child ON child.oid = inheritance.inhrelid
            JOIN pg_catalog.pg_namespace AS child_namespace
              ON child_namespace.oid = child.relnamespace
            WHERE parent_namespace.nspname = :parent_schema
              AND parent.relname = :parent_table
              AND parent.relkind = 'p'
              AND child.relispartition
            """
        ),
        {
            "parent_schema": _SNAPSHOT_PARENT_SCHEMA,
            "parent_table": _SNAPSHOT_PARENT_TABLE,
        },
    )
    return frozenset((row.child_schema, row.child_name) for row in rows)


def include_name_without_partitions(
    partition_names: frozenset[tuple[str, str]],
    default_schema_name: str,
) -> Callable[[str | None, str, dict[str, str | None]], bool]:
    def include_name(
        name: str | None,
        object_type: str,
        parent_names: dict[str, str | None],
    ) -> bool:
        schema_name = parent_names.get("schema_name") or default_schema_name
        return not (
            object_type == "table" and name is not None and (schema_name, name) in partition_names
        )

    return include_name


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        with connection.begin():
            partition_names = snapshot_partition_names(connection)
        default_schema_name = connection.dialect.default_schema_name or _SNAPSHOT_PARENT_SCHEMA
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=include_name_without_partitions(partition_names, default_schema_name),
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
