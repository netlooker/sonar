# Sonar

Sonar is a deterministic live-web search, fetch, and extraction service for agents.

It complements local-memory systems such as Synapse:

- Synapse owns private memory and semantic retrieval.
- Sonar owns fresh external evidence from the web.

Sonar v1 is intentionally narrow:

- external SearxNG for metasearch
- deterministic query planning and ranking
- cached fetch and extraction artifacts in SQLite
- thin HTTP/OpenAPI and MCP adapters
- no LLM reasoning layer in the core path

## Quick Start

1. Install the project:

```bash
uv sync --extra dev
```

2. Copy the tracked config template:

```bash
cp config/sonar.example.toml config/sonar.toml
```

3. Adjust local values in `config/sonar.toml` and optional overlays in `secrets/`.

4. Start the API:

```bash
uv run sonar-api
```

5. Or start the MCP server:

```bash
SONAR_CONFIG=/ABSOLUTE/PATH/TO/config/sonar.toml uv run sonar-mcp
```

## Container

Build the API image:

```bash
docker build -t sonar:latest .
```

Run it with a local config mounted into `/app/config/sonar.toml`:

```bash
docker run --rm -p 8001:8001 \
  -e SONAR_CONFIG=/app/config/sonar.toml \
  -v "$(pwd)/config/sonar.toml:/app/config/sonar.toml:ro" \
  -v sonar-data:/data \
  sonar:latest
```

For containers, point the database path in `config/sonar.toml` at a mounted location such as `/data/sonar.sqlite`.

## Compose

Run Sonar together with a dedicated SearxNG service:

```bash
docker compose up --build
```

This stack uses:

- Sonar API on `http://127.0.0.1:8001`
- SearxNG as an internal service at `http://searxng:8080`
- a named Docker volume for Sonar's SQLite state

Tracked local-stack files:

- `docker-compose.yml`
- `config/sonar.compose.example.toml`
- `searxng/settings.yml`

## Surface

HTTP routes:

- `GET /health`
- `POST /search`
- `POST /fetch`
- `POST /extract`

MCP tools:

- `sonar_health`
- `sonar_search`
- `sonar_fetch`
- `sonar_extract`

## Docs

- [Architecture](docs/architecture.md)
- [HTTP API](docs/http-api.md)
- [MCP Requirements](docs/mcp-requirements.md)
- [Quick Start](docs/quick-start.md)
- [OpenAPI](docs/openapi.json)
