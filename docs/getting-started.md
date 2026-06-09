# Getting Started

This guide covers the supported ways to start Sonar and verify a working
installation.

## Compose MCP

The fastest agent-integration path starts Streamable HTTP MCP and SearxNG
together:

```bash
docker compose --profile mcp up --build sonar-mcp
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`. Configure OpenCode with
[`../config/opencode.mcp.example.json`](../config/opencode.mcp.example.json),
then verify:

```bash
opencode mcp list
```

Use the connected agent to:

1. Call `sonar_health`.
2. Call `sonar_search` for a topic.
3. Select a relevant result and call `sonar_scrape` on its URL.

Stop the stack with:

```bash
docker compose --profile mcp down
```

## Compose HTTP API

Start the HTTP API and SearxNG:

```bash
docker compose up --build
```

Verify health and search:

```bash
curl http://127.0.0.1:8001/health

curl -X POST http://127.0.0.1:8001/search \
  -H 'content-type: application/json' \
  -d '{"query":"Python release notes","limit":3}'
```

See the [HTTP API guide](guides/http-api.md) for additional examples.

## Local Installation

Install development dependencies and create a local configuration:

```bash
uv sync --extra dev
cp config/sonar.example.toml config/sonar.toml
```

Point `[searxng].base_url` at a reachable SearxNG instance. The default is
`http://127.0.0.1:8080`.

Start stdio MCP:

```bash
SONAR_CONFIG=config/sonar.toml uv run sonar-mcp
```

Start Streamable HTTP MCP:

```bash
SONAR_CONFIG=config/sonar.toml \
SONAR_MCP_TRANSPORT=streamable-http \
uv run sonar-mcp
```

Start the HTTP API:

```bash
SONAR_CONFIG=config/sonar.toml uv run sonar-api
```

## Optional Features

Install optional resilient-retrieval dependencies:

```bash
uv sync --extra dev --extra resilient --extra browser
```

Then enable the desired backends in configuration. See
[Resilient Retrieval](guides/resilient-retrieval.md).

Topic relevance filtering uses an OpenAI-compatible embeddings endpoint. Supply
`SONAR_EMBEDDINGS_API_KEY` or `OPENAI_API_KEY` when using it. Topic collection
continues with a warning if embeddings are unavailable.

## Troubleshooting

- **MCP client cannot connect:** confirm `docker compose --profile mcp ps` shows
  `sonar-mcp` running and the client URL ends in `/mcp`.
- **Search fails:** confirm SearxNG is reachable from Sonar and supports JSON
  search responses.
- **Local MCP exits immediately:** `SONAR_CONFIG` is required when starting
  `sonar-mcp`.
- **Browser fallback is skipped:** install optional dependencies and enable the
  relevant retrieval settings.
- **A URL is denied:** robots and policy denials are terminal by design.

Run `uv run sonar-smoke --config config/sonar.toml` for runtime diagnostics.
