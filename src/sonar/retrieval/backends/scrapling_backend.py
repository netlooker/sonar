"""Optional Scrapling HTTP retrieval backend."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from time import perf_counter

from sonar.errors import (
    SonarBodyTooLargeError,
    SonarDependencyError,
    SonarUpstreamUnavailableError,
)

from ..models import RetrievalBackend
from .base import BackendResult


def retrieve_with_scrapling(
    *,
    url: str,
    timeout_seconds: float,
    max_body_bytes: int,
    validate_url: Callable[[str], None] | None = None,
) -> BackendResult:
    try:
        from scrapling.fetchers import Fetcher
    except ImportError as exc:
        raise SonarDependencyError(
            "Scrapling retrieval is not installed.", dependency="scrapling"
        ) from exc

    started = perf_counter()
    try:
        page = Fetcher.get(url, timeout=timeout_seconds, follow_redirects=False)
    except Exception as exc:
        raise SonarUpstreamUnavailableError("Scrapling HTTP retrieval failed.") from exc
    body = bytes(getattr(page, "body", b"") or b"")
    if len(body) > max_body_bytes:
        raise SonarBodyTooLargeError(
            "Fetched document exceeded the configured body-size limit."
        )
    raw_headers = getattr(page, "headers", {}) or {}
    headers = (
        {str(key).lower(): str(value) for key, value in raw_headers.items()}
        if isinstance(raw_headers, Mapping)
        else {}
    )
    final_url = str(getattr(page, "url", None) or url)
    if validate_url:
        validate_url(final_url)
    status_code = getattr(page, "status", None)
    if status_code is not None and 300 <= status_code < 400:
        raise SonarUpstreamUnavailableError(
            "Scrapling HTTP retrieval returned an unvalidated redirect."
        )
    return BackendResult(
        backend=RetrievalBackend.SCRAPLING_HTTP,
        final_url=final_url,
        status_code=status_code,
        content_type=headers.get("content-type", "").split(";")[0].strip().lower(),
        body=body,
        rendered=False,
        duration_ms=int((perf_counter() - started) * 1000),
    )
