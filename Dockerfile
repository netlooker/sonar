FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra api --no-install-project

COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra api

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH \
    SONAR_HTTP_HOST=0.0.0.0 \
    SONAR_HTTP_PORT=8001

RUN useradd --create-home --home-dir /app --uid 10001 sonar

WORKDIR /app

COPY --from=builder --chown=sonar:sonar /app/.venv /app/.venv
COPY --from=builder --chown=sonar:sonar /app/src /app/src
COPY --chown=sonar:sonar README.md pyproject.toml ./
COPY --chown=sonar:sonar config/sonar.example.toml ./config/sonar.example.toml
COPY --chown=sonar:sonar docs ./docs

RUN mkdir -p /app/config /app/secrets /data && chown -R sonar:sonar /app /data

USER sonar

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import json,urllib.request;json.load(urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=3))"

CMD ["sonar-api"]
