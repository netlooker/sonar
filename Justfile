set dotenv-load := true

default:
    @just --list

# Install development dependencies.
setup:
    uv sync --extra dev

# Install development and optional resilient-retrieval dependencies.
setup-all:
    uv sync --extra dev --extra resilient --extra browser

# Run the test suite.
test:
    uv run pytest

# Run Ruff lint checks.
lint:
    uvx ruff check .

# Format Python files with Ruff.
format:
    uvx ruff format .

# Verify Python formatting without modifying files.
format-check:
    uvx ruff format --check .

# Run documentation contract tests.
docs-check:
    uv run pytest tests/test_documentation.py

# Run all repository checks.
check: lint format-check docs-check test

# Regenerate the tracked OpenAPI schema.
openapi:
    uv run sonar-export-openapi

# Start the local HTTP API.
api:
    uv run sonar-api

# Start the local stdio MCP server.
mcp:
    SONAR_CONFIG="${SONAR_CONFIG:-config/sonar.toml}" uv run sonar-mcp

# Start the local Streamable HTTP MCP server.
mcp-http:
    SONAR_CONFIG="${SONAR_CONFIG:-config/sonar.toml}" SONAR_MCP_TRANSPORT=streamable-http uv run sonar-mcp

# Run runtime health checks; pass a query with `just smoke "query"`.
smoke query="":
    #!/usr/bin/env bash
    set -euo pipefail
    args=(--config "${SONAR_CONFIG:-config/sonar.toml}")
    if [[ -n "{{query}}" ]]; then
      args+=(--query "{{query}}")
    fi
    uv run sonar-smoke "${args[@]}"

# Start the HTTP API and SearxNG Compose stack.
compose-up:
    docker compose up --build

# Start the Streamable HTTP MCP and SearxNG Compose stack.
compose-mcp:
    docker compose --profile mcp up --build sonar-mcp

# Stop all Compose services, including profiled services.
compose-down:
    docker compose --profile mcp down

# Validate the default and MCP Compose configurations.
compose-check:
    docker compose config --quiet
    docker compose --profile mcp config --quiet
