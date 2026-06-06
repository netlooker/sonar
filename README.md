# Sonar

Sonar is a deterministic live-web search, fetch, and extraction service for agents.

It complements local-memory systems such as Synapse:

- Synapse owns private memory and semantic retrieval.
- Sonar owns fresh external evidence from the web.

Sonar v1 is intentionally narrow:

- external SearxNG for metasearch
- deterministic query planning and ranking
- cached fetch and extraction artifacts in SQLite
- optional policy-aware Scrapling and CloakBrowser fallback for difficult HTML
- multi-format document extraction for HTML, PDF, DOCX, ODT, Markdown, and text
- durable prepared-source bundle persistence for high-level research flows
- thin HTTP/OpenAPI and MCP adapters
- optional high-level paper-preparation facade for weaker local agents
- no LLM reasoning layer in the core path

Notable high-level behavior:

- PDF responses and direct `.pdf` URLs are extracted with `pymupdf` and carried through to prepared bundle `full_text`
- `collect-sources` applies a semantic relevance filter over collected source abstracts/summaries before returning the final source list

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

   If you want topic relevance filtering in `collect-sources`, also configure an embeddings API key through `OPENAI_API_KEY` or `SONAR_EMBEDDINGS_API_KEY`.

4. Start the API:

```bash
uv run sonar-api
```

5. Or start the MCP server:

```bash
SONAR_CONFIG=/ABSOLUTE/PATH/TO/config/sonar.toml uv run sonar-mcp
```

For a remote MCP endpoint:

```bash
SONAR_CONFIG=/ABSOLUTE/PATH/TO/config/sonar.toml \
SONAR_MCP_TRANSPORT=streamable-http \
uv run sonar-mcp
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

Build the optional browser-capable Streamable HTTP MCP image with:

```bash
docker build --target browser-runtime -t sonar:browser .
```

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
- `POST /find-papers`
- `POST /prepare-paper-set`
- `POST /collect-sources`

MCP tools:

- `sonar_health`
- `sonar_search`
- `sonar_fetch`
- `sonar_extract`
- `sonar_find_papers`
- `sonar_prepare_paper_set`
- `sonar_collect_sources_for_topic`

The raw MCP tool names are unprefixed (`health`, `search`, `extract`, and so
on). Most clients prepend the configured connection name, so an OpenCode
connection named `sonar` displays `sonar_search` rather than
`sonar_sonar_search`.

The normal low-level workflow is search followed by extract for selected URLs.
Extract performs retrieval itself; fetch is available for metadata probes and
cache warming but is not required before extract.
The paper-preparation tools collapse the retrieval loop for weaker local runtimes and return structured source bundles instead of requiring repeated orchestration.
`prepare-paper-set` and `collect-sources` now auto-persist durable prepared bundles by default, including a JSON manifest and optional text sidecars for extracted source content.
`collect-sources` over-collects paper candidates, then prunes low-relevance items with semantic similarity before returning and persisting the final bundle. If embeddings are unavailable, the filter is skipped and a warning is returned instead.

## Config Notes

Important extraction and topic-filter settings:

- `fetch.max_body_bytes` controls the maximum fetched payload size for extractable documents, including PDFs
- `embeddings.enabled` enables semantic topic-result filtering for `collect-sources`
- `embeddings.base_url` and `embeddings.model` point at an OpenAI-compatible `/embeddings` API
- `embeddings.similarity_threshold` sets the minimum cosine similarity required to keep a candidate in topic collection
- `embeddings.api_key` can be supplied with `SONAR_EMBEDDINGS_API_KEY` or `OPENAI_API_KEY`

## Synapse Handoff

The intended downstream flow stays:

- call `prepare-paper-set` or `collect-sources`
- persist the prepared bundle manifest
- hand `prepared_source_bundle.json` to Synapse ingest
- let Synapse own indexing, knowledge compile, and review

For Synapse-facing prepared bundles, `bundle_version = 1` is the current compatibility contract.
Synapse normalizes from the core prepared-source fields and tolerates extra metadata, so Sonar can keep adding non-breaking bundle details around that stable handoff surface.

## Docs

- [Architecture](docs/architecture.md)
- [HTTP API](docs/http-api.md)
- [MCP Requirements](docs/mcp-requirements.md)
- [Quick Start](docs/quick-start.md)
- [OpenAPI](docs/openapi.json)
