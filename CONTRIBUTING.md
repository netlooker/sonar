# Contributing

Sonar requires Python 3.12 or newer and uses `uv` for dependency management.
Docker and Compose are needed only for container workflow changes.

## Setup

```bash
uv sync --extra dev
```

Install optional resilient-retrieval dependencies when working on those
backends:

```bash
uv sync --extra dev --extra resilient --extra browser
```

The equivalent optional shortcuts are `just setup` and `just setup-all`.

## Checks

Run the complete repository check before submitting a change:

```bash
uvx ruff check .
uvx ruff format --check .
uv run pytest
```

Or run:

```bash
just check
```

Use `uvx ruff format .` or `just format` to format Python files. Validate
Compose changes with `just compose-check`.

## OpenAPI

`docs/openapi.json` is generated from the FastAPI application and is checked by
the test suite. After an intentional HTTP contract change, regenerate it with:

```bash
uv run sonar-export-openapi
```

Or run `just openapi`, then review the schema diff.

## Documentation

- Keep adopter documentation task-oriented and standalone.
- Document raw commands even when a `just` shortcut exists.
- Link to the configuration reference instead of duplicating every option.
- Document only artifacts and interfaces produced by the current code.
- Keep historical release details in `docs/releases/`.

Run focused documentation checks with:

```bash
uv run pytest tests/test_documentation.py
```
