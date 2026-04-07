# Nyx Update - 2026-04-07

## Implemented

Sonar now treats high-level prepared-source output as a first-class durable artifact.

- `prepare-paper-set` and `collect-sources` now auto-persist prepared bundles by default.
- High-level responses now include a canonical `bundle` object while retaining compatibility `sources` fields.
- Persisted bundles write `prepared_source_bundle.json` plus optional `source_XX.txt` sidecars.
- Bundle provenance now includes stable `source_id`, origin URL, retrieval timestamps, extraction method/status, cache flags, search lineage, and bundle-level request fingerprinting.
- SQLite now tracks prepared bundle registry state in addition to document/search caches.

## Extraction Improvements

Low-level extraction remains the same API shape, but is now format-aware.

- Added extraction support for HTML, PDF, DOCX, ODT, Markdown, and plain text.
- Direct PDF and other direct-document candidates are no longer skipped by the high-level preparation flow.
- Landing-page preparation can merge HTML metadata with direct-document full text when a supported direct document URL is discoverable.
- High-level source metadata now separates `summary`, `abstract`, and `full_text`.

## Downstream Impact

This makes Sonar materially better as upstream infrastructure for Synapse and other weaker/local agents.

- Important retrieval evidence is no longer dependent on transcript retention.
- Prepared bundles are inspectable on disk and auditable by bundle ID.
- Downstream note-writing and indexing can target persisted Sonar artifacts directly.

## Verification

- `uv run pytest -q`
- Result: `40 passed`

## Remaining Limitation

Direct-document discovery from landing pages is still heuristic-based in this iteration. The current implementation explicitly covers common academic patterns including arXiv, OpenReview, ACL Anthology, and PMLR, but it is not yet a generalized document-link resolver.
