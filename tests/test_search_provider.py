import httpx

from sonar.search_providers import SearxNGProvider


def test_searxng_provider_parses_json_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search"
        assert request.url.params["q"] == "latest ai"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "AI Search",
                        "url": "https://example.com/a",
                        "content": "Latest AI search news",
                        "engine": "duckduckgo",
                        "publishedDate": "2025-01-01T00:00:00Z",
                    }
                ]
            },
        )

    provider = SearxNGProvider(
        base_url="http://searx.local",
        transport=httpx.MockTransport(handler),
    )
    results = provider.search("latest ai")

    assert results[0].title == "AI Search"
    assert results[0].engine == "duckduckgo"
    assert results[0].published_at == "2025-01-01T00:00:00Z"
