# MCP Requirements

Sonar MCP exposes the same deterministic service layer used by HTTP.

Initial tool surface:

- `sonar_health`
- `sonar_search`
- `sonar_fetch`
- `sonar_extract`
- `sonar_find_papers`
- `sonar_prepare_paper_set`
- `sonar_collect_sources_for_topic`

Tool roles:

- `sonar_search`, `sonar_fetch`, and `sonar_extract` stay as the canonical composable MCP API.
- `sonar_find_papers`, `sonar_prepare_paper_set`, and `sonar_collect_sources_for_topic` provide a smaller workflow surface for weaker local models by collapsing search, filtering, and extraction into fewer interactions.

Runtime requirements:

- Python environment with Sonar installed
- reachable SearxNG instance
- writable SQLite database path
- local `SONAR_CONFIG` file
