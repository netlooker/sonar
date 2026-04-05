import hashlib
import json

import httpx
import pytest

from sonar.errors import SonarBadRequestError, SonarForbiddenError
from sonar.service_api import (
    ExtractRequest,
    FetchRequest,
    HealthRequest,
    SearchRequest,
    extract_document_record,
    fetch_document_record,
    runtime_requirements,
    search_web,
)


def test_runtime_requirements_reports_readiness(tmp_path):
    response = runtime_requirements(HealthRequest(config_path="config/sonar.example.toml", db_path=str(tmp_path / "sonar.sqlite")))

    assert response.database_path == str(tmp_path / "sonar.sqlite")
    assert response.searxng_base_url == "http://127.0.0.1:8080"


def test_search_web_caches_results(tmp_path):
    calls = {"search": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["search"] += 1
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "SearxNG Result",
                        "url": "https://example.com/a?utm_source=x",
                        "content": "query result",
                        "engine": "duckduckgo",
                    }
                ]
            },
        )

    request = SearchRequest(
        query="latest ai search",
        config_path="config/sonar.example.toml",
        db_path=str(tmp_path / "sonar.sqlite"),
    )

    first = search_web(request, transport=httpx.MockTransport(handler))
    second = search_web(request, transport=httpx.MockTransport(handler))

    assert first.from_cache is False
    assert second.from_cache is True
    assert calls["search"] == 1
    assert second.results[0].canonical_url == "https://example.com/a"


def test_search_web_force_refresh_bypasses_cache(tmp_path):
    calls = {"search": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search":
            calls["search"] += 1
            return httpx.Response(
                200,
                json={"results": [{"title": "One", "url": "https://example.com/1", "content": "one", "engine": "ddg"}]},
            )
        return httpx.Response(404)

    request = SearchRequest(
        query="latest ai search",
        config_path="config/sonar.example.toml",
        db_path=str(tmp_path / "sonar.sqlite"),
    )

    search_web(request, transport=httpx.MockTransport(handler))
    search_web(request.model_copy(update={"force_refresh": True}), transport=httpx.MockTransport(handler))

    assert calls["search"] == 2


def test_search_web_rejects_empty_query(tmp_path):
    with pytest.raises(SonarBadRequestError):
        search_web(
            SearchRequest(query="   ", config_path="config/sonar.example.toml", db_path=str(tmp_path / "sonar.sqlite"))
        )


def test_fetch_document_honors_robots_and_caches(tmp_path):
    calls = {"page": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/page":
            calls["page"] += 1
            return httpx.Response(200, text="<html><title>Page</title><body>Hello world</body></html>", headers={"content-type": "text/html"})
        return httpx.Response(404)

    req = FetchRequest(
        url="https://example.com/page",
        config_path="config/sonar.example.toml",
        db_path=str(tmp_path / "sonar.sqlite"),
    )
    first = fetch_document_record(req, transport=httpx.MockTransport(handler))
    second = fetch_document_record(req, transport=httpx.MockTransport(handler))

    assert first.from_cache is False
    assert second.from_cache is True
    assert calls["page"] == 1


def test_fetch_document_robots_blocked(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(404)

    with pytest.raises(SonarForbiddenError):
        fetch_document_record(
            FetchRequest(
                url="https://example.com/private",
                config_path="config/sonar.example.toml",
                db_path=str(tmp_path / "sonar.sqlite"),
            ),
            transport=httpx.MockTransport(handler),
        )


def test_extract_document_uses_cached_text(tmp_path):
    canonical_url = "https://example.com/page"
    document_id = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
    db = tmp_path / "sonar.sqlite"
    fetch_document_record(
        FetchRequest(url=canonical_url, config_path="config/sonar.example.toml", db_path=str(db), force_refresh=True),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="User-agent: *\nAllow: /\n")
            if request.url.path == "/robots.txt"
            else httpx.Response(200, text="<html><body>Page</body></html>", headers={"content-type": "text/html"})
        ),
    )

    import sonar.service_api as service_api

    def fake_extract(body: bytes, *, url: str):
        return type(
            "Extracted",
            (),
            {
                "title": "Example",
                "byline": None,
                "published_at": None,
                "language": "en",
                "excerpt": "Page",
                "text": "Page body",
                "word_count": 2,
            },
        )()

    original = service_api.extract_document
    service_api.extract_document = fake_extract
    try:
        first = extract_document_record(
            ExtractRequest(document_id=document_id, config_path="config/sonar.example.toml", db_path=str(db)),
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text="User-agent: *\nAllow: /\n")
                if request.url.path == "/robots.txt"
                else httpx.Response(200, text="<html><body>Page</body></html>", headers={"content-type": "text/html"})
            ),
        )
        second = extract_document_record(
            ExtractRequest(document_id=document_id, config_path="config/sonar.example.toml", db_path=str(db)),
            transport=httpx.MockTransport(lambda request: httpx.Response(500)),
        )
    finally:
        service_api.extract_document = original

    assert first.from_cache is False
    assert second.from_cache is True
    assert second.text == "Page body"
