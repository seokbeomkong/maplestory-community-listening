FROM ghcr.io/astral-sh/uv:0.11.28 AS uv

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN groupadd --gid 10001 maple \
    && useradd --uid 10001 --gid maple --create-home --shell /usr/sbin/nologin maple

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev && uv pip check

COPY --chown=maple:maple alembic.ini ./alembic.ini
COPY --chown=maple:maple alembic ./alembic
COPY --chown=maple:maple config ./config

USER maple

CMD ["maple-monitor", "health"]
