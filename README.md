# Sonar

Sonar is a deterministic live-web search, retrieval, and extraction service for
agents. It exposes a focused MCP and HTTP surface backed by SearxNG, SQLite
caching, multi-format extraction, and optional resilient retrieval for difficult
HTML.

Use Sonar when an agent needs fresh web evidence without placing an LLM in the
retrieval path.

## Capabilities

- Ranked and deduplicated web search through SearxNG
- One-call MCP scraping for known URLs
- Extraction from HTML, PDF, DOCX, ODT, Markdown, and plain text
- Optional Scrapling and CloakBrowser fallback for difficult HTML
- Policy-aware retrieval with robots and local-network protections
- Durable prepared-source bundles for research workflows
- Stdio and Streamable HTTP MCP transports
- JSON HTTP API with a tracked [OpenAPI schema](docs/openapi.json)

## Five-Minute MCP Start

Requirements: Docker with Compose.

Start Sonar MCP and its SearxNG dependency:

```bash
docker compose --profile mcp up --build sonar-mcp
```

Sonar is now available over Streamable HTTP at
`http://127.0.0.1:8000/mcp`.

For OpenCode, merge the contents of
[`config/opencode.mcp.example.json`](config/opencode.mcp.example.json) into your
OpenCode configuration, then verify the connection:

```bash
opencode mcp list
```

Ask the agent to check `sonar_health`, search for a topic with `sonar_search`,
and scrape one selected result with `sonar_scrape`.

Stop the stack with:

```bash
docker compose --profile mcp down
```

See [Getting Started](docs/getting-started.md) for local stdio MCP, the HTTP API,
configuration, and troubleshooting.

## Tool Surface

MCP tools:

- `health`
- `search`
- `fetch`
- `scrape`
- `extract`
- `find_papers`
- `prepare_paper_set`
- `collect_sources_for_topic`

MCP clients commonly prefix tools with the configured connection name. An
OpenCode connection named `sonar` therefore exposes `sonar_search` and
`sonar_scrape`.

HTTP routes:

- `GET /health`
- `POST /search`
- `POST /fetch`
- `POST /extract`
- `POST /find-papers`
- `POST /prepare-paper-set`
- `POST /collect-sources`

## Deployment Choices

- **Compose MCP:** fastest path for agent integrations.
- **Local stdio MCP:** best when a client should launch Sonar directly.
- **HTTP API:** suitable for applications that do not use MCP.
- **Browser runtime image:** includes optional resilient retrieval dependencies.

The default installation and image remain lightweight. Browser fallback is
opt-in and applies only to difficult HTML; non-HTML documents never use it.
Policy and robots denials are terminal.

## Documentation

- [Getting Started](docs/getting-started.md)
- [MCP Guide](docs/guides/mcp.md)
- [HTTP API Guide](docs/guides/http-api.md)
- [Resilient Retrieval](docs/guides/resilient-retrieval.md)
- [Prepared Bundles](docs/guides/prepared-bundles.md)
- [Configuration Reference](docs/reference/configuration.md)
- [Architecture](docs/architecture.md)
- [Contributing](CONTRIBUTING.md)

`just` is available as an optional convenience interface. Run `just --list` to
see recipes; every guide also shows the underlying commands.
