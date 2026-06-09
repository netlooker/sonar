# Prepared Bundles

Sonar's high-level research tools can return and persist durable prepared-source
bundles:

- `prepare_paper_set`
- `collect_sources_for_topic`

## Persistence

Persistence is enabled by default. Each bundle is stored under
`~/.sonar/bundles/<bundle_id>/` unless `output_dir` is supplied.

The directory contains:

```text
prepared_source_bundle.json
source_01.txt
source_02.txt
...
```

`prepared_source_bundle.json` is the canonical manifest. Text sidecars are
written only when `include_sidecars=true` and a source has full text.

## Contract

`bundle_version = 1` is the current compatibility boundary. Prepared sources
separate:

- `summary`: compact high-level description
- `abstract`: abstract-level description when available
- `full_text`: extracted source text
- `full_text_path`: optional persisted text sidecar

Sources also include stable identifiers, origin and direct-document URLs,
authors, publication metadata, extraction status, retrieval timestamps, cache
state, and retrieval provenance.

Direct PDF and other supported document candidates participate in normal
preparation flows. PDF body text is preserved as `full_text`.

## Topic Relevance

`collect_sources_for_topic` over-collects candidates and can prune
low-similarity results with an OpenAI-compatible embeddings provider. If
embeddings are unavailable, collection continues without semantic pruning and
returns a warning.

## Downstream Integration

Downstream systems should ingest `prepared_source_bundle.json` as the canonical
handoff and read `source_XX.txt` sidecars only when needed. Synapse is one
example of a consumer of this stable prepared-bundle contract.
