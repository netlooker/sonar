"""Search providers for Sonar."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from .errors import SonarTimeoutError, SonarUpstreamUnavailableError


@dataclass(frozen=True)
class SearchProviderResult:
    title: str
    url: str
    snippet: str
    engine: str
    position: int
    published_at: str | None = None


class SearxNGProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        authorization_header: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.authorization_header = authorization_header
        self.transport = transport
        self.timeout = timeout

    def search(
        self,
        query: str,
        *,
        engines: list[str] | None = None,
        categories: list[str] | None = None,
        language: str | None = None,
        freshness: str = "any",
    ) -> list[SearchProviderResult]:
        params = {
            "q": query,
            "format": "json",
        }
        if engines:
            params["engines"] = ",".join(engines)
        if categories:
            params["categories"] = ",".join(categories)
        if language:
            params["language"] = language
        if freshness != "any":
            params["time_range"] = freshness

        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if self.authorization_header:
            headers["Authorization"] = self.authorization_header

        client = httpx.Client(transport=self.transport, timeout=self.timeout)
        try:
            response = client.get(f"{self.base_url}/search", params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise SonarTimeoutError(
                "SearxNG search timed out.",
                timeout_seconds=self.timeout,
            ) from exc
        except httpx.HTTPError as exc:
            raise SonarUpstreamUnavailableError("SearxNG search request failed.") from exc
        finally:
            client.close()

        results = []
        for position, item in enumerate(payload.get("results", []), start=1):
            engine_value = item.get("engine") or ",".join(item.get("engines", []) or []) or "searxng"
            results.append(
                SearchProviderResult(
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    snippet=str(item.get("content", item.get("snippet", ""))),
                    engine=str(engine_value),
                    position=position,
                    published_at=item.get("publishedDate"),
                )
            )
        return results
