# HTTP API Guide

Sonar exposes a local-first JSON API on `http://127.0.0.1:8001` by default.
Start it with Compose:

```bash
docker compose up --build
```

## Health

```bash
curl http://127.0.0.1:8001/health
```

The response reports runtime requirements and optional backend availability.

## Search

```bash
curl -X POST http://127.0.0.1:8001/search \
  -H 'content-type: application/json' \
  -d '{"query":"Python release notes","limit":3,"freshness":"month"}'
```

Search results are normalized, deduplicated, ranked, and cached.

## Extract a Known URL

```bash
curl -X POST http://127.0.0.1:8001/extract \
  -H 'content-type: application/json' \
  -d '{"url":"https://docs.python.org/3/whatsnew/"}'
```

`extract` retrieves and extracts a URL in one request. It also accepts a cached
`document_id`. Use `fetch` only when response metadata or cache warming is the
goal.

## Prepare Research Sources

```bash
curl -X POST http://127.0.0.1:8001/collect-sources \
  -H 'content-type: application/json' \
  -d '{"topic":"retrieval augmented generation","max_results":3,"corpus":"papers"}'
```

`prepare-paper-set` and `collect-sources` can persist prepared bundles by
default. See [Prepared Bundles](prepared-bundles.md).

## Routes

- `GET /health`
- `POST /search`
- `POST /fetch`
- `POST /extract`
- `POST /find-papers`
- `POST /prepare-paper-set`
- `POST /collect-sources`

The complete request and response contract is available in the tracked
[OpenAPI schema](../openapi.json).
