"""HTTP fetch utilities."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from .errors import SonarForbiddenError, SonarTimeoutError, SonarUpstreamUnavailableError
from .extract import detect_source_format


@dataclass(frozen=True)
class FetchArtifact:
    url: str
    final_url: str
    status: str
    status_code: int
    content_type: str
    body: bytes | None
    extractable: bool
    source_format: str | None


def fetch_url(
    *,
    url: str,
    user_agent: str,
    connect_timeout_seconds: float,
    read_timeout_seconds: float,
    max_body_bytes: int,
    transport: httpx.BaseTransport | None = None,
    include_body: bool = False,
) -> FetchArtifact:
    timeout = httpx.Timeout(connect=connect_timeout_seconds, read=read_timeout_seconds, write=read_timeout_seconds, pool=read_timeout_seconds)
    client = httpx.Client(
        timeout=timeout,
        headers={"User-Agent": user_agent},
        follow_redirects=True,
        transport=transport,
    )
    try:
        _assert_allowed_by_robots(client, url, user_agent)
        with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            final_url = str(response.url)
            source_format = detect_source_format(url=final_url, content_type=content_type)
            extractable = source_format is not None
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > max_body_bytes:
                    raise SonarUpstreamUnavailableError("Fetched document exceeded the configured body-size limit.")
                if include_body:
                    chunks.append(chunk)
            return FetchArtifact(
                url=url,
                final_url=final_url,
                status="fetched",
                status_code=response.status_code,
                content_type=content_type,
                body=b"".join(chunks) if include_body else None,
                extractable=extractable,
                source_format=source_format,
            )
    except SonarForbiddenError:
        raise
    except httpx.TimeoutException as exc:
        raise SonarTimeoutError("Document fetch timed out.", timeout_seconds=read_timeout_seconds) from exc
    except httpx.HTTPStatusError as exc:
        raise SonarUpstreamUnavailableError(
            f"Document fetch failed with status {exc.response.status_code}."
        ) from exc
    except httpx.HTTPError as exc:
        raise SonarUpstreamUnavailableError("Document fetch failed.") from exc
    finally:
        client.close()


def _assert_allowed_by_robots(client: httpx.Client, url: str, user_agent: str) -> None:
    parts = urlsplit(url)
    robots_url = urljoin(f"{parts.scheme}://{parts.netloc}", "/robots.txt")
    try:
        response = client.get(robots_url)
    except httpx.HTTPError as exc:
        raise SonarUpstreamUnavailableError("robots.txt request failed.") from exc

    if response.status_code == 404:
        return
    if response.status_code in {401, 403}:
        raise SonarForbiddenError("robots.txt disallows access to this site.")
    if response.status_code >= 500:
        raise SonarUpstreamUnavailableError("robots.txt request failed.")

    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    if not parser.can_fetch(user_agent, url):
        raise SonarForbiddenError("robots.txt disallows access to this URL.")
