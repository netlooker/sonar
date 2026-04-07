# Architecture

Sonar is a deterministic live-web evidence engine for agents.

It has three layers:

1. typed settings and runtime resolution
2. deterministic service core
3. thin transport adapters for HTTP and MCP

Core responsibilities:

- search via an external SearxNG instance
- deterministic query normalization and variant generation
- URL canonicalization and dedupe
- ranking with freshness and domain priors
- cached fetch metadata
- readable-text extraction across HTML, PDF, DOCX, ODT, Markdown, and text
- metadata persistence for fetched documents and prepared-source bundle registries
- durable prepared-source manifests for downstream handoff to note-writing and indexing systems

Design rules:

- deterministic mechanics first
- no mandatory reasoning backend
- transport adapters stay thin
- tracked configs stay public-safe
