# Quick Start

1. Install dependencies:

```bash
uv sync --extra dev
```

2. Copy the example config:

```bash
cp config/sonar.example.toml config/sonar.toml
```

3. Adjust the SearxNG URL and database path.

4. If you plan to use `collect-sources` topic filtering, configure an embeddings API key:

```bash
export OPENAI_API_KEY=...
```

   Or:

```bash
export SONAR_EMBEDDINGS_API_KEY=...
```

5. Run the API:

```bash
uv run sonar-api
```

6. Or run the MCP server:

```bash
SONAR_CONFIG=/ABSOLUTE/PATH/TO/config/sonar.toml uv run sonar-mcp
```

For remote MCP clients, run Streamable HTTP:

```bash
SONAR_CONFIG=/ABSOLUTE/PATH/TO/config/sonar.toml \
SONAR_MCP_TRANSPORT=streamable-http \
SONAR_MCP_HOST=0.0.0.0 \
uv run sonar-mcp
```

The endpoint is `http://HOST:8000/mcp` by default.

## Optional Resilient Retrieval

The default install and image keep the normal HTTP fast path and do not include
browser dependencies. Enable optional backends only when needed:

```bash
uv sync --extra dev --extra resilient --extra browser
```

Then set `retrieval.scrapling_enabled = true` and, for rendered fallback, both
`retrieval.browser_enabled = true` and
`retrieval.cloakbrowser_enabled = true`. If an enabled optional backend is not
installed, Sonar records that failed attempt and retains the best usable prior
result. Policy and robots denials remain terminal.

## Container Build

Build the lightweight API image:

```bash
docker build -t sonar:latest .
```

Run:

```bash
docker run --rm -p 8001:8001 \
  -e SONAR_CONFIG=/app/config/sonar.toml \
  -v "$(pwd)/config/sonar.toml:/app/config/sonar.toml:ro" \
  -v sonar-data:/data \
  sonar:latest
```

Build the browser-capable Streamable HTTP MCP target:

```bash
docker build --target browser-runtime -t sonar:browser .
docker run --rm -p 8000:8000 -v sonar-data:/data sonar:browser
```

The browser target pins the published CloakBrowser multi-architecture image
digest used for this release.

## Compose Stack

Start Sonar with a colocated SearxNG backend:

```bash
docker compose up --build
```

The compose stack mounts:

- `config/sonar.compose.example.toml` into the Sonar container
- `searxng/settings.yml` into the SearxNG container
- a named volume for `/data/sonar.sqlite`

## Notes

- PDF extraction requires `pymupdf`, which is now part of Sonar's runtime dependencies.
- `collect-sources` can run without embeddings, but semantic relevance filtering is skipped in that case and the response includes a warning.
