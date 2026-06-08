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
- `collect-sources` performs an additional semantic relevance pass over collected results and removes low-similarity sources before returning the final bundle when embeddings are configured.

Prepared bundle behavior:

- High-level requests accept `persist`, `output_dir`, and `include_sidecars`.
- Persisted bundles write `prepared_source_bundle.json` plus optional `source_XX.txt` files.
- Low-level extraction is format-aware for HTML, PDF, DOCX, ODT, Markdown, and plain text.
- Fetch and extract responses add `retrieval_backend`, `rendered`,
  `retrieval_attempts`, `retrieval_warnings`, and `fallback_reason`.
- Difficult HTML can escalate from the normal HTTP path to optional Scrapling
  HTTP and CloakBrowser backends. Non-HTML formats never use browser fallback.
- Robots and retrieval-policy denials are terminal.
- PDF extraction uses `pymupdf`, and extracted PDF body text is preserved in `full_text` for prepared sources.
- Topic collection scores each candidate against the original topic using embeddings derived from `abstract`, `summary`, or search snippet text.
- If the embeddings provider is unavailable or unconfigured, topic collection continues without the semantic filter and returns a warning.

Synapse handoff:

- Run `prepare-paper-set` or `collect-sources`.
- Persist the returned bundle manifest.
- Hand `prepared_source_bundle.json` to Synapse ingest.
- Let Synapse handle indexing, compiled knowledge, and review.

Compatibility contract:

- `bundle_version = 1` is the current Sonar contract for Synapse-facing prepared bundles.
- Synapse is expected to normalize from these core source fields:
  `source_id`, `title`, `origin_url`, `direct_paper_url`, `authors`, `published`, `summary`,
  `abstract`, `full_text`, `full_text_path`, `source_type`, `retrieved_at`,
  `extraction_status`, and `extraction_method`.
- Extra bundle metadata is allowed as long as those fields remain stable.
- Retrieval provenance is additive metadata and does not change
  `bundle_version = 1`.

Default bind:

- host: `127.0.0.1`
- port: `8001`

Tracked OpenAPI export:

- [openapi.json](openapi.json)
