"""Policy-aware ordered retrieval orchestration."""

from __future__ import annotations

import socket

import httpx

from sonar.errors import SonarError, SonarUpstreamUnavailableError
from sonar.extract import (
    ExtractArtifact,
    HTML_CONTENT_TYPES,
    detect_source_format,
    extract_document,
)
from sonar.settings import AppSettings

from .backends import (
    retrieve_with_cloakbrowser,
    retrieve_with_httpx,
    retrieve_with_scrapling,
)
from .backends.base import BackendResult
from .heuristics import assess_html_fallback
from .models import (
    FallbackReason,
    RetrievalArtifact,
    RetrievalAttempt,
    RetrievalBackend,
)
from .policy import assert_backend_allowed

RetrievalCandidate = tuple[BackendResult, ExtractArtifact | None, FallbackReason | None]


def retrieve_url(
    *,
    url: str,
    settings: AppSettings,
    transport: httpx.BaseTransport | None = None,
) -> RetrievalArtifact:
    attempts: list[RetrievalAttempt] = []
    warnings: list[str] = []
    best: RetrievalCandidate | None = None
    pending_reason: FallbackReason | None = None
    backend_url = url

    backends = [RetrievalBackend.HTTP]
    if settings.retrieval.scrapling_enabled:
        backends.append(RetrievalBackend.SCRAPLING_HTTP)
    if settings.retrieval.browser_enabled and settings.retrieval.cloakbrowser_enabled:
        backends.append(RetrievalBackend.CLOAKBROWSER)

    for backend in backends:
        if backend is not RetrievalBackend.HTTP and pending_reason is None:
            break
        escalation_reason = (
            pending_reason if backend is not RetrievalBackend.HTTP else None
        )
        if escalation_reason is not None:
            warnings.append(
                f"{escalation_reason.value}_triggered_{backend.value}_fallback"
            )
        _assert_allowed(backend_url, backend, settings, transport)
        try:
            result = _run_backend(
                backend=backend, url=backend_url, settings=settings, transport=transport
            )
        except SonarError as exc:
            if exc.error_type in {
                "forbidden",
                "bad_request",
                "body_too_large",
                "robots_unavailable",
            }:
                raise
            attempts.append(
                RetrievalAttempt(
                    backend=backend, outcome="failed", warnings=(exc.error_type,)
                )
            )
            warnings.append(f"{backend.value}_failed")
            if not _may_use_html_fallback(
                url=backend_url,
                content_type="",
                source_format=detect_source_format(url=backend_url, content_type=None),
            ):
                break
            pending_reason = FallbackReason.TRANSPORT_FAILURE
            continue

        source_format = detect_source_format(
            url=result.final_url, content_type=result.content_type
        )
        extracted = None
        fallback_reason = None
        may_use_html_fallback = _may_use_html_fallback(
            url=result.final_url,
            content_type=result.content_type,
            source_format=source_format,
            status_code=result.status_code,
        )
        if may_use_html_fallback and result.body is not None:
            try:
                extracted = extract_document(
                    result.body, url=result.final_url, content_type=result.content_type
                )
            except SonarError:
                extracted = None
            fallback_reason = assess_html_fallback(
                status_code=result.status_code,
                body=result.body,
                extracted=extracted,
                thin_text_min_chars=settings.retrieval.thin_text_min_chars,
            )
        attempts.append(
            RetrievalAttempt(
                backend=backend,
                outcome="retrieved",
                status_code=result.status_code,
                rendered=result.rendered,
                duration_ms=result.duration_ms,
                fallback_reason=fallback_reason,
            )
        )
        best = _choose_best(best, (result, extracted, escalation_reason))
        backend_url = result.final_url
        pending_reason = fallback_reason
        if not may_use_html_fallback or fallback_reason is None:
            break

    if (
        attempts
        and attempts[-1].outcome == "retrieved"
        and attempts[-1].fallback_reason is not None
        and attempts[-1].backend is backends[-1]
    ):
        warnings.append(f"{attempts[-1].fallback_reason.value}_fallback_not_available")

    if best is None:
        raise SonarUpstreamUnavailableError("All configured retrieval backends failed.")

    result, extracted, final_reason = best
    if final_reason is None:
        final_reason = next(
            (
                attempt.fallback_reason
                for attempt in attempts
                if attempt.backend is result.backend
                and attempt.fallback_reason is not None
            ),
            None,
        )
    if result.body is None or result.status_code is None:
        raise SonarUpstreamUnavailableError(
            "Retrieval returned no usable document body."
        )
    if result.status_code >= 400:
        raise SonarUpstreamUnavailableError(
            f"Document fetch failed with status {result.status_code}."
        )
    source_format = detect_source_format(
        url=result.final_url, content_type=result.content_type
    )
    return RetrievalArtifact(
        url=url,
        final_url=result.final_url,
        status="fetched",
        status_code=result.status_code,
        content_type=result.content_type,
        body=result.body,
        extractable=source_format is not None,
        source_format=source_format,
        backend=result.backend,
        rendered=result.rendered,
        attempts=tuple(attempts),
        warnings=tuple(warnings),
        fallback_reason=final_reason,
        extracted=extracted,
    )


def _run_backend(
    *,
    backend: RetrievalBackend,
    url: str,
    settings: AppSettings,
    transport: httpx.BaseTransport | None,
) -> BackendResult:
    common = {
        "url": url,
        "max_body_bytes": settings.fetch.max_body_bytes,
    }
    if backend is RetrievalBackend.HTTP:
        return retrieve_with_httpx(
            **common,
            user_agent=settings.fetch.user_agent,
            connect_timeout_seconds=settings.fetch.connect_timeout_seconds,
            read_timeout_seconds=settings.fetch.read_timeout_seconds,
            respect_robots=settings.policy.respect_robots,
            transport=transport,
            validate_url=lambda target: _assert_allowed(
                target,
                RetrievalBackend.HTTP,
                settings,
                transport,
            ),
        )
    if backend is RetrievalBackend.SCRAPLING_HTTP:
        return retrieve_with_scrapling(
            **common,
            timeout_seconds=settings.fetch.read_timeout_seconds,
            validate_url=lambda target: _assert_allowed(
                target,
                RetrievalBackend.SCRAPLING_HTTP,
                settings,
                transport,
            ),
        )
    return retrieve_with_cloakbrowser(
        **common,
        timeout_seconds=settings.fetch.read_timeout_seconds,
        wait_until=settings.retrieval.browser_wait_until,
        validate_url=lambda target: _assert_allowed(
            target,
            RetrievalBackend.CLOAKBROWSER,
            settings,
            transport,
        ),
    )


def _choose_best(
    current: RetrievalCandidate | None, candidate: RetrievalCandidate
) -> RetrievalCandidate:
    if current is None:
        return candidate
    current_result, current_extracted, _ = current
    candidate_result, candidate_extracted, _ = candidate
    if candidate_result.status_code is not None and candidate_result.status_code >= 400:
        return current
    if current_result.status_code is not None and current_result.status_code >= 400:
        return candidate
    current_length = len(current_extracted.text) if current_extracted else 0
    candidate_length = len(candidate_extracted.text) if candidate_extracted else 0
    if candidate_length > current_length:
        return candidate
    return current


def _assert_allowed(
    url: str,
    backend: RetrievalBackend,
    settings: AppSettings,
    transport: httpx.BaseTransport | None,
) -> None:
    resolver = _mock_public_resolver if transport is not None else socket.getaddrinfo
    assert_backend_allowed(url, backend, settings, resolver=resolver)


def _mock_public_resolver(hostname: str, port: int, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


def _may_use_html_fallback(
    *,
    url: str,
    content_type: str,
    source_format: str | None,
    status_code: int | None = None,
) -> bool:
    target_format = detect_source_format(url=url, content_type=None)
    if target_format not in {None, "html"}:
        return False
    if status_code in {401, 403, 429}:
        return source_format not in {"pdf", "docx", "odt", "markdown"}
    if source_format is not None:
        return source_format == "html"
    normalized_type = content_type.split(";")[0].strip().lower()
    return not normalized_type or normalized_type in HTML_CONTENT_TYPES
