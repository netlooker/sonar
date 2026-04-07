# HTTP API

Sonar exposes a local-first JSON API for web clients.

Routes:

- `GET /health`
- `POST /search`
- `POST /fetch`
- `POST /extract`
- `POST /find-papers`
- `POST /prepare-paper-set`
- `POST /collect-sources`

Route roles:

- `search`, `fetch`, and `extract` remain the canonical low-level transport surface.
- `find-papers`, `prepare-paper-set`, and `collect-sources` provide a higher-level facade for agent runtimes that struggle with multi-step retrieval orchestration.
- `prepare-paper-set` and `collect-sources` return a first-class `bundle` object and persist durable prepared-source artifacts by default.

Prepared bundle behavior:

- High-level requests accept `persist`, `output_dir`, and `include_sidecars`.
- Persisted bundles write `prepared_source_bundle.json` plus optional `source_XX.txt` files.
- Low-level extraction is format-aware for HTML, PDF, DOCX, ODT, Markdown, and plain text.

Default bind:

- host: `127.0.0.1`
- port: `8001`

Tracked OpenAPI export:

- [openapi.json](openapi.json)
