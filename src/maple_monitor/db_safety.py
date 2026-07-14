from __future__ import annotations

import re
from urllib.parse import unquote

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


_ALLOWED_DRIVERS = {"postgresql", "postgresql+psycopg"}
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_TEST_DATABASE_NAME = "maple_monitor_test"
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_ROUTING_QUERY_KEYS = {
    "conninfo",
    "database",
    "dbname",
    "dsn",
    "host",
    "hostaddr",
    "password",
    "port",
    "service",
    "servicefile",
    "user",
}
_CONTRACT_ERROR = "DATABASE_URL must target the isolated PostgreSQL test database on loopback"


class UnsafeTestDatabaseUrlError(ValueError):
    """Raised without echoing a rejected database URL or its credentials."""


def _contains_control_character(value: str) -> bool:
    return any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)


def validate_isolated_test_database_url(value: str | None) -> URL:
    """Parse and validate the exact URL semantics consumed by SQLAlchemy/libpq."""
    if value is None or not value.strip():
        raise UnsafeTestDatabaseUrlError(f"{_CONTRACT_ERROR}; DATABASE_URL is missing")

    if "#" in value or _contains_control_character(value) or _INVALID_PERCENT_ESCAPE.search(value):
        raise UnsafeTestDatabaseUrlError(f"{_CONTRACT_ERROR}; DATABASE_URL is malformed")

    try:
        decoded_value = unquote(value, errors="strict")
        if _contains_control_character(decoded_value):
            raise UnicodeError
        url = make_url(value)
        port = url.port
    except (ArgumentError, TypeError, UnicodeError, ValueError):
        raise UnsafeTestDatabaseUrlError(f"{_CONTRACT_ERROR}; DATABASE_URL is malformed") from None

    query_keys = {key.casefold() for key in url.query}
    if (
        url.drivername not in _ALLOWED_DRIVERS
        or url.host is None
        or url.host.casefold() not in _LOOPBACK_HOSTS
        or url.database != _TEST_DATABASE_NAME
        or (port is not None and not 1 <= port <= 65_535)
        or bool(query_keys & _ROUTING_QUERY_KEYS)
    ):
        raise UnsafeTestDatabaseUrlError(_CONTRACT_ERROR)

    return url
