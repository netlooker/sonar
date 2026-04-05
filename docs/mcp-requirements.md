# MCP Requirements

Sonar MCP exposes the same deterministic service layer used by HTTP.

Initial tool surface:

- `sonar_health`
- `sonar_search`
- `sonar_fetch`
- `sonar_extract`

Runtime requirements:

- Python environment with Sonar installed
- reachable SearxNG instance
- writable SQLite database path
- local `SONAR_CONFIG` file
