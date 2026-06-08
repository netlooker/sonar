"""Backend result shared by retrieval adapters."""

from __future__ import annotations

from dataclasses import dataclass

from sonar.retrieval.models import RetrievalBackend


@dataclass(frozen=True)
class BackendResult:
    backend: RetrievalBackend
    final_url: str
    status_code: int | None
    content_type: str
    body: bytes | None
    rendered: bool
    duration_ms: int
    warnings: tuple[str, ...] = ()
