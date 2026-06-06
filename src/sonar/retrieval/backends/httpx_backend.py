"""Existing Sonar HTTP retrieval backend."""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from urllib.parse import urljoin

import httpx

from sonar.errors import (
    SonarBodyTooLargeError,
    SonarTimeoutError,
    SonarUpstreamUnavailableError,
)

from ..models import RetrievalBackend
from ..robots import assert_allowed_by_robots
from .base import BackendResult


def retrieve_with_httpx(
    *,
    url: str,
    user_agent: str,
    connect_timeout_seconds: float,
    read_timeout_seconds: float,
    max_body_bytes: int,
    respect_robots: bool,
    transport: httpx.BaseTransport | None = None,
    validate_url: Callable[[str], None] | None = None,
) -> BackendResult:
    started = perf_counter()
    timeout = httpx.Timeout(
        connect=connect_timeout_seconds,
        read=read_timeout_seconds,
        write=read_timeout_seconds,
        pool=read_timeout_seconds,
    )
    client = httpx.Client(
        timeout=timeout,
        headers={"User-Agent": user_agent},
        follow_redirects=False,
        transport=transport,
    )
    try:
        current_url = url
        for _ in range(11):
            if validate_url:
                validate_url(current_url)
            if respect_robots:
                assert_allowed_by_robots(client, current_url, user_agent)
            with client.stream("GET", current_url) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise SonarUpstreamUnavailableError(
                            "Document redirect omitted a location."
                        )
                    current_url = urljoin(str(response.url), location)
                    continue
                content_type = (
                    response.headers.get("content-type", "")
                    .split(";")[0]
                    .strip()
                    .lower()
                )
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_body_bytes:
                        raise SonarBodyTooLargeError(
                            "Fetched document exceeded the configured body-size limit."
                        )
                    chunks.append(chunk)
                return BackendResult(
                    backend=RetrievalBackend.HTTP,
                    final_url=str(response.url),
                    status_code=response.status_code,
                    content_type=content_type,
                    body=b"".join(chunks),
                    rendered=False,
                    duration_ms=int((perf_counter() - started) * 1000),
                )
        raise SonarUpstreamUnavailableError("Document exceeded the redirect limit.")
    except (SonarUpstreamUnavailableError,):
        raise
    except httpx.TimeoutException as exc:
        raise SonarTimeoutError(
            "Document fetch timed out.", timeout_seconds=read_timeout_seconds
        ) from exc
    except httpx.HTTPError as exc:
        raise SonarUpstreamUnavailableError("Document fetch failed.") from exc
    finally:
        client.close()
