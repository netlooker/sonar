"""Typed retrieval contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from sonar.extract import ExtractArtifact


class RetrievalBackend(StrEnum):
    HTTP = "http"
    SCRAPLING_HTTP = "scrapling_http"
    CLOAKBROWSER = "cloakbrowser"


class FallbackReason(StrEnum):
    TRANSPORT_FAILURE = "transport_failure"
    HTTP_401 = "http_401"
    HTTP_403 = "http_403"
    HTTP_429 = "http_429"
    RESTRICTION_MARKER = "restriction_marker"
    APP_SHELL = "app_shell"
    THIN_TEXT = "thin_text"
    EMPTY_EXTRACTION = "empty_extraction"


@dataclass(frozen=True)
class RetrievalAttempt:
    backend: RetrievalBackend
    outcome: str
    status_code: int | None = None
    rendered: bool = False
    duration_ms: int = 0
    warnings: tuple[str, ...] = ()
    fallback_reason: FallbackReason | None = None


@dataclass(frozen=True)
class RetrievalArtifact:
    url: str
    final_url: str
    status: str
    status_code: int
    content_type: str
    body: bytes
    extractable: bool
    source_format: str | None
    backend: RetrievalBackend
    rendered: bool = False
    attempts: tuple[RetrievalAttempt, ...] = ()
    warnings: tuple[str, ...] = ()
    fallback_reason: FallbackReason | None = None
    extracted: ExtractArtifact | None = field(default=None, repr=False)
