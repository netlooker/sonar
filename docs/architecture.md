# Architecture

Sonar is a deterministic live-web evidence service with four layers:

1. Typed settings and runtime resolution
2. Policy-aware retrieval and deterministic extraction
3. Service orchestration and SQLite persistence
4. Thin HTTP and MCP transport adapters

## Retrieval Flow

Search requests go to an external SearxNG instance, then Sonar normalizes,
deduplicates, ranks, and caches the results.

Known URLs use the normal HTTP backend first. Difficult HTML may use optional
Scrapling and CloakBrowser fallback. Policy is checked before every live
attempt, and policy or robots denial is terminal. Retrieved bodies and
provenance are cached so later extraction can avoid duplicate requests.

Extraction is deterministic and format-aware for HTML, PDF, DOCX, ODT,
Markdown, and plain text.

## Service Surface

The service core owns search, fetch, extraction, paper discovery, prepared
source collection, and durable bundle persistence. HTTP and MCP adapters map
those operations without adding reasoning behavior.

## Design Rules

- No mandatory LLM or reasoning backend in the core path
- Deterministic mechanics before transport concerns
- Thin transport adapters
- Additive SQLite migrations
- Browser fallback is opt-in and HTML-only
- Policy and robots denials are terminal
- Tracked configuration remains public-safe
- Prepared bundles preserve the `bundle_version = 1` compatibility boundary
