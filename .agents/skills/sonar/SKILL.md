---
name: sonar
description: Live-web search, retrieval, and text extraction via Sonar MCP tools.
user-invocable: true
disable-model-invocation: false
---

# Sonar MCP

Use Sonar for deterministic live-web evidence. It searches through SearxNG,
ranks and deduplicates results, retrieves URLs, and extracts readable text. No
LLM sits in the core retrieval path.

## Available Tools

| Tool | Purpose | Key params |
|------|---------|------------|
| `sonar_health` | Check runtime readiness | none |
| `sonar_search` | Discover ranked candidate URLs | `query`, `limit`, `freshness`, `force_refresh` |
| `sonar_fetch` | Probe and cache URL metadata | `url`, `force_refresh` |
| `sonar_scrape` | Retrieve and extract a known URL in one call | `url`, `force_refresh`, `include_text`, `max_chars` |
| `sonar_extract` | Extract a URL or cached document ID | `url` or `document_id`, `force_refresh`, `include_text`, `max_chars` |
| `sonar_find_papers` | Discover scientific paper candidates | `query`, `count`, `profile` |
| `sonar_prepare_paper_set` | Prepare and persist a scientific paper set | `query`, `count`, `profile`, `direct_only` |
| `sonar_collect_sources_for_topic` | Prepare and persist a topic-focused bundle | `topic`, `max_results`, `corpus` |

## Workflow Choice

For normal web discovery:

1. Call `sonar_search`.
2. Select only relevant result URLs.
3. Call `sonar_scrape` for those URLs.

When a URL is already known, call `sonar_scrape` directly. Use
`sonar_extract` for a cached `document_id`, and use `sonar_fetch` only when
response status, content type, redirect metadata, or cache warming is needed.

For scientific papers or topic research, prefer
`sonar_prepare_paper_set` or `sonar_collect_sources_for_topic`. Treat the
returned `bundle` as the canonical handoff.

## Practical Patterns

```text
sonar_scrape(url="https://example.com/article")
```

```text
sonar_prepare_paper_set(query="retrieval augmented generation", count=5, profile="scientific", direct_only=true)
```

```text
sonar_collect_sources_for_topic(topic="retrieval augmented generation", max_results=5, corpus="papers")
```

## Prepared Bundles

Persisted bundle directories contain:

```text
prepared_source_bundle.json
source_01.txt
source_02.txt
...
```

`prepared_source_bundle.json` is the canonical manifest. Text sidecars are
optional and exist only for sources with persisted full text.

Prepared sources separate `summary`, `abstract`, and `full_text`. Direct PDFs
and other supported documents participate in normal preparation flows.

Topic collection may over-collect candidates and prune low-similarity sources
with embeddings. If embeddings are unavailable, Sonar returns results without
semantic pruning and includes a warning.

## Important Constraints

- Robots and retrieval-policy denials are terminal.
- Browser fallback is opt-in and applies only to difficult HTML.
- Extracted text can be large; MCP text responses are truncated by default.
- Cache state and retrieval provenance are included in responses.
- `document_id` refers to a previously fetched or searched document.
