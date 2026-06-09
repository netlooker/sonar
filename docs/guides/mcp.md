# MCP Guide

Sonar exposes the same deterministic service layer over stdio and Streamable
HTTP MCP.

## OpenCode Remote MCP

Start the Compose MCP profile:

```bash
docker compose --profile mcp up --build sonar-mcp
```

Add this entry to your OpenCode configuration:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "sonar": {
      "type": "remote",
      "url": "http://127.0.0.1:8000/mcp",
      "enabled": true
    }
  }
}
```

Verify it with:

```bash
opencode mcp list
```

OpenCode prefixes raw tool names with the connection name. A connection named
`sonar` exposes `sonar_search`, not `sonar_sonar_search`.

## Generic Transports

Start a local stdio server:

```bash
SONAR_CONFIG=config/sonar.toml uv run sonar-mcp
```

Start a remote Streamable HTTP server:

```bash
SONAR_CONFIG=config/sonar.toml \
SONAR_MCP_TRANSPORT=streamable-http \
SONAR_MCP_HOST=0.0.0.0 \
uv run sonar-mcp
```

The default Streamable HTTP endpoint is `http://HOST:8000/mcp`.

## Tool Choice

- `health`: diagnose runtime readiness.
- `search`: discover ranked candidate URLs.
- `scrape`: retrieve and extract a known URL in one call.
- `extract`: extract a URL or cached document ID.
- `fetch`: inspect and cache response metadata.
- `find_papers`: discover scientific paper candidates.
- `prepare_paper_set`: prepare and persist a scientific paper set.
- `collect_sources_for_topic`: prepare and persist a topic-focused source
  bundle.

The normal discovery workflow is `search`, select relevant URLs, then `scrape`.
When a URL is already known, call `scrape` directly.

`scrape` and `extract` return at most 12,000 text characters by default. Set
`include_text=false` or adjust `max_chars` up to the 50,000-character hard
limit.

## Runtime Requirements

- Python environment with Sonar and the `mcp` extra installed
- Reachable SearxNG instance
- Writable SQLite database path
- Existing `SONAR_CONFIG` file

Streamable HTTP settings are documented in the
[Configuration Reference](../reference/configuration.md).
