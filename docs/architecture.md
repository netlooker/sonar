# Architecture

Sonar is a deterministic live-web evidence engine for agents.

It has four layers:

1. typed settings and runtime resolution
2. policy-aware retrieval backends and deterministic extraction
3. deterministic service core
4. thin transport adapters for HTTP and MCP

Core responsibilities:

- search via an external SearxNG instance
- deterministic query normalization and variant generation
- URL canonicalization and dedupe
- ranking with freshness and domain priors
- cached retrieval bodies, metadata, and provenance
- optional Scrapling HTTP and CloakBrowser fallback for difficult HTML
- readable-text extraction across HTML, PDF, DOCX, ODT, Markdown, and text
- metadata persistence for fetched documents and prepared-source bundle registries
- durable prepared-source manifests for downstream handoff to note-writing and indexing systems
- a stable prepared-bundle compatibility boundary for Synapse ingest via `bundle_version = 1`

Design rules:

- deterministic mechanics first
- no mandatory reasoning backend
- transport adapters stay thin
- policy and robots denials are terminal
- browser fallback is opt-in and HTML-only
- tracked configs stay public-safe
