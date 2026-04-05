"""Readable-text extraction utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .errors import SonarDependencyError, SonarUpstreamUnavailableError


@dataclass(frozen=True)
class ExtractArtifact:
    canonical_url: str
    title: str | None
    byline: str | None
    published_at: str | None
    language: str | None
    excerpt: str | None
    text: str
    word_count: int


def extract_document(html: bytes, *, url: str) -> ExtractArtifact:
    try:
        import trafilatura
    except ImportError as exc:  # pragma: no cover - installation path
        raise SonarDependencyError(
            "Trafilatura is required for extraction.",
            dependency="trafilatura",
            retryable=False,
        ) from exc

    decoded = html.decode("utf-8", errors="ignore")
    payload = trafilatura.extract(
        decoded,
        url=url,
        with_metadata=True,
        output_format="json",
        include_comments=False,
        include_tables=False,
    )
    if not payload:
        raise SonarUpstreamUnavailableError("Readable text extraction returned no content.", retryable=False)
    parsed = json.loads(payload)
    text = str(parsed.get("text", "")).strip()
    if not text:
        raise SonarUpstreamUnavailableError("Readable text extraction returned empty text.", retryable=False)
    return ExtractArtifact(
        canonical_url=str(parsed.get("url", url)),
        title=_nullable_str(parsed.get("title")),
        byline=_nullable_str(parsed.get("author")),
        published_at=_nullable_str(parsed.get("date")),
        language=_nullable_str(parsed.get("language")),
        excerpt=_nullable_str(parsed.get("excerpt")),
        text=text,
        word_count=len(text.split()),
    )


def trafilatura_available() -> bool:
    try:
        import trafilatura  # noqa: F401
    except ImportError:
        return False
    return True


def _nullable_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
