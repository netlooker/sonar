---
name: sonar
description: Live-web search, fetch, and text extraction via Sonar MCP tools.
user-invocable: true
disable-model-invocation: false
---

# Sonar MCP

Sonar is a deterministic live-web evidence engine. It searches the web through
SearXNG, ranks and deduplicates results, fetches URLs, and extracts readable
text. No LLM sits in the core retrieval path.

Recent Sonar behavior that matters operationally:

- PDF responses and direct `.pdf` URLs are extracted with `pymupdf`
- extracted PDF body text now flows into prepared bundle `full_text`
- `sonar_collect_sources_for_topic` now applies a semantic relevance filter over
  collected source abstracts and summaries before returning the final bundle
  when embeddings are configured

## Available tools

| Tool | Purpose | Key params |
|------|---------|------------|
| `sonar_health` | Check runtime readiness | none |
| `sonar_search` | Search the live web and return ranked evidence | `query`, `limit`, `freshness`, `engines`, `categories`, `language`, `force_refresh` |
| `sonar_fetch` | Fetch one URL and cache its metadata | `url`, `force_refresh` |
| `sonar_extract` | Extract readable text from a URL or cached document | `url` or `document_id`, `force_refresh`, `include_text`, `max_chars` |
| `sonar_find_papers` | Return curated scientific paper candidates for a topic | `query`, `count`, `profile` |
| `sonar_prepare_paper_set` | Search, filter, and extract a prepared scientific paper set in one call | `query`, `count`, `profile`, `direct_only` |
| `sonar_collect_sources_for_topic` | Return a compact structured source bundle for a topic | `topic`, `max_results`, `corpus` |

All Sonar tools are deterministic.

## Workflow Choice

### Preferred high-level flow

1. Start with `sonar_prepare_paper_set`, `sonar_find_papers`, or `sonar_collect_sources_for_topic`
2. Treat the returned `bundle` object as the canonical source handoff
3. Read the persisted summary artifact first, then the compact manifest, then per-source sidecars only as needed
4. Use the low-level tools only when you need tighter control over ranking, fetch, or extraction

For topic-driven research, prefer `sonar_collect_sources_for_topic` over manual
search loops when you want Sonar to prune false positives automatically. It now
over-collects candidates and drops low-similarity sources with an embeddings
pass before persisting the final bundle.

Preferred read order for weaker local models:

1. `prepared_sources_bundle.md`
2. `prepared_source_manifest.json`
3. `source_XX.json` or `source_XX.txt` only for the specific sources you are using
4. `prepared_source_bundle.json` only if the compact manifest is missing or inconsistent

### Manual flow

1. `sonar_search`
2. Select only the relevant result URLs
3. `sonar_extract` those selected URLs

`sonar_extract` performs retrieval itself and does not require a preceding
`sonar_fetch` call. Use `sonar_fetch` only when you specifically need response
status, content type, redirect metadata, or cache warming. Use `sonar_health`
for diagnostics rather than normal research.

## Practical patterns

### Prepare a scientific paper set in one call

```text
sonar_prepare_paper_set(query="prompt engineering scientific papers", count=5, profile="scientific", direct_only=true)
```

### Collect a compact source bundle for a topic

```text
sonar_collect_sources_for_topic(topic="prompt engineering", max_results=5, corpus="papers")
```

Use this when broad keyword matching would likely admit off-topic papers. The
topic flow now has a semantic post-filter, so it is the safer default for
query-driven paper collection.

### Persist the prepared source set before note writing

```text
bundle = sonar_collect_sources_for_topic(topic="prompt engineering", max_results=5, corpus="papers")
```

Inspect `bundle["bundle_path"]` and the persisted artifacts before
summarizing them.

### Canonical persisted artifacts

```text
prepared_sources_bundle.md
prepared_source_manifest.json
prepared_source_bundle.json
source_01.txt
source_02.txt
...
```

When a prepared source is PDF-backed, expect the extracted paper body to be in
`full_text` or the text sidecar rather than falling back to metadata-only
bundle content.

## Search parameters

- `freshness`: `any`, `day`, `week`, `month`
- `limit`: default 8, max 20
- `engines` / `categories`: optional SearXNG filters
- `language`: optional BCP-47 tag
- `force_refresh`: bypasses cache

## Configuration

Key config sections:

- `[searxng]`: SearXNG base URL
- `[database]`: SQLite path
- `[cache]`: TTLs for search and extract results
- `[fetch]`: timeouts, max body size, user agent
- `[retrieval]`: optional Scrapling and browser fallback behavior
- `[policy]`: robots and local-network retrieval policy
- `[domains]`: optional per-domain and per-backend policy overrides
- `[search]`: default and max result limits
- `[embeddings]`: semantic topic-filter provider settings for `sonar_collect_sources_for_topic`
- `[ranking.domain_priors]`: per-domain score bonuses
- `[secrets]`: path to secrets overlay for provider auth or overrides

Important embeddings settings:

- `embeddings.enabled`
- `embeddings.base_url`
- `embeddings.model`
- `embeddings.similarity_threshold`
- `SONAR_EMBEDDINGS_API_KEY` or `OPENAI_API_KEY` for provider auth

If embeddings are missing or the provider fails,
`sonar_collect_sources_for_topic` still returns results, but the semantic
post-filter is skipped and Sonar emits a warning. Do not assume topic bundles
were semantically pruned unless you inspect the warning list or know the
runtime is configured.

## Prepared Bundle Semantics

The high-level facade separates:

- `summary`: compact high-level description
- `abstract`: abstract-level paper description when available
- `full_text`: extracted full source text

It also records provenance fields such as stable `source_id`, retrieval
timestamps, extraction method/status, cache flags, and search lineage.

Direct-document candidates such as PDFs are part of the normal high-level
preparation flow when the format is supported. Do not assume PDF-first academic
sources will be skipped.

For topic collection specifically, treat the final returned bundle as the
post-filtered truth set. Sonar may search and prepare more candidates than the
final `selected_count`, then prune low-relevance items before returning the
bundle you see.

## Important constraints

- `robots.txt` is respected automatically unless the runtime config explicitly changes that behavior
- Extracted text can be large
- `document_id` in `sonar_extract` refers to a previously fetched or searched document
- Cache is per query signature
