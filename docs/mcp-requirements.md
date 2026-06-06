# MCP Requirements

Sonar MCP exposes the same deterministic service layer used by HTTP.

Raw MCP tool surface:

- `health`
- `search`
- `fetch`
- `extract`
- `find_papers`
- `prepare_paper_set`
- `collect_sources_for_topic`

Tool roles:

- MCP clients commonly namespace these names with the configured connection
  name. An OpenCode connection named `sonar` therefore exposes `sonar_search`,
  not `sonar_sonar_search`.
- The normal composable workflow is `search` followed by `extract` for selected
  URLs. `fetch` is a metadata probe and is not required before extraction.
- Operator-only paths and configuration overrides are not exposed to agents.
- Stdio remains the default transport; Streamable HTTP is supported at `/mcp`.
- `extract` defaults to returning at most 12,000 text characters to reduce
  agent context pressure. Agents can set `include_text=false` or adjust
  `max_chars` up to the 50,000-character hard limit.

Runtime requirements:

- Python environment with Sonar installed
- reachable SearxNG instance
- writable SQLite database path
- local `SONAR_CONFIG` file

Streamable HTTP environment:

- `SONAR_MCP_TRANSPORT=streamable-http`
- `SONAR_MCP_HOST`, `SONAR_MCP_PORT`, and `SONAR_MCP_PATH`
- `SONAR_MCP_STATELESS_HTTP` defaults to `true`
