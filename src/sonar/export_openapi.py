"""Export the tracked OpenAPI schema."""

from __future__ import annotations

import json
from pathlib import Path

from .web_api import create_app


def main() -> None:
    output = Path("docs/openapi.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(create_app().openapi(), indent=2), encoding="utf-8")
