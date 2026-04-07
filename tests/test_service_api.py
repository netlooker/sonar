import hashlib
import json

import httpx
import pytest

from sonar.errors import SonarBadRequestError, SonarForbiddenError
from sonar.service_api import (
    CollectSourcesForTopicRequest,
    ExtractRequest,
    ExtractResponse,
    FetchRequest,
    FindPapersRequest,
    HealthRequest,
    PreparePaperSetRequest,
    PreparePaperSetResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    collect_sources_for_topic,
    extract_document_record,
    fetch_document_record,
    find_papers,
    prepare_paper_set,
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


def test_find_papers_prefers_direct_scientific_results(monkeypatch, tmp_path):
    search_response = SearchResponse(
        query="llm reasoning",
        variants=["llm reasoning"],
        run_id="run-1",
        partial_results=False,
        from_cache=True,
        results=[
            SearchResult(
                title="Semantic Scholar listing for reasoning papers",
                url="https://www.semanticscholar.org/search?q=llm%20reasoning",
                canonical_url="https://www.semanticscholar.org/search?q=llm+reasoning",
                snippet="catalog of papers",
                engine="ddg",
                position=1,
                domain="www.semanticscholar.org",
                score=2.2,
            ),
            SearchResult(
                title="Reasoning with language models",
                url="https://arxiv.org/abs/2401.12345",
                canonical_url="https://arxiv.org/abs/2401.12345",
                snippet="research preprint abstract",
                engine="ddg",
                position=2,
                domain="arxiv.org",
                published_at="2024-01-15",
                score=1.6,
            ),
            SearchResult(
                title="Reasoning benchmark",
                url="https://openreview.net/forum?id=abc123",
                canonical_url="https://openreview.net/forum?id=abc123",
                snippet="conference paper",
                engine="ddg",
                position=3,
                domain="openreview.net",
                published_at="2024-02-01",
                score=1.4,
            ),
        ],
    )

    monkeypatch.setattr("sonar.service_api.search_web", lambda request, transport=None: search_response)

    response = find_papers(
        FindPapersRequest(
            query="llm reasoning",
            config_path="config/sonar.example.toml",
            db_path=str(tmp_path / "sonar.sqlite"),
            count=2,
        )
    )

    assert [candidate.url for candidate in response.candidates] == [
        "https://arxiv.org/abs/2401.12345",
        "https://openreview.net/forum?id=abc123",
    ]
    assert all(candidate.source_type == "paper_landing_page" for candidate in response.candidates)
    assert all(candidate.from_search_cache is True for candidate in response.candidates)


def test_prepare_paper_set_uses_larger_candidate_pool_than_requested(monkeypatch, tmp_path):
    search_response = SearchResponse(
        query="tool use",
        variants=["tool use"],
        run_id="run-2",
        partial_results=False,
        results=[
            SearchResult(
                title="Tool Use Paper PDF",
                url="https://arxiv.org/pdf/2401.00001.pdf",
                canonical_url="https://arxiv.org/pdf/2401.00001.pdf",
                snippet="paper pdf",
                engine="ddg",
                position=1,
                domain="arxiv.org",
                score=2.5,
            ),
            SearchResult(
                title="Tool use with agents",
                url="https://arxiv.org/abs/2401.00002",
                canonical_url="https://arxiv.org/abs/2401.00002",
                snippet="research abstract",
                engine="ddg",
                position=2,
                domain="arxiv.org",
                score=1.0,
            ),
            SearchResult(
                title="Toolformer replication",
                url="https://openreview.net/forum?id=toolformer",
                canonical_url="https://openreview.net/forum?id=toolformer",
                snippet="conference paper",
                engine="ddg",
                position=3,
                domain="openreview.net",
                score=0.9,
            ),
            SearchResult(
                title="Agent systems",
                url="https://aclanthology.org/2024.findings-acl.1/",
                canonical_url="https://aclanthology.org/2024.findings-acl.1/",
                snippet="proceedings paper",
                engine="ddg",
                position=4,
                domain="aclanthology.org",
                score=0.8,
            ),
        ],
    )
    extracts = {
        "https://arxiv.org/abs/2401.00002": ExtractResponse(
            document_id="doc-1",
            canonical_url="https://arxiv.org/abs/2401.00002",
            title="Tool use with agents",
            byline="Alice Example, Bob Example",
            published_at="2024-01-10",
            excerpt="Abstract one",
            text="Abstract one full text",
            word_count=4,
            from_cache=False,
        ),
        "https://openreview.net/forum?id=toolformer": ExtractResponse(
            document_id="doc-2",
            canonical_url="https://openreview.net/forum?id=toolformer",
            title="Toolformer replication",
            byline="Carol Example and Dan Example",
            published_at="2024-02-10",
            excerpt="Abstract two",
            text="Abstract two full text",
            word_count=4,
            from_cache=True,
        ),
        "https://aclanthology.org/2024.findings-acl.1/": ExtractResponse(
            document_id="doc-3",
            canonical_url="https://aclanthology.org/2024.findings-acl.1/",
            title="Agent systems",
            byline="Eve Example",
            published_at="2024-03-10",
            excerpt=None,
            text="First paragraph of extracted paper text for testing summaries.",
            word_count=9,
            from_cache=False,
        ),
    }

    monkeypatch.setattr("sonar.service_api.search_web", lambda request, transport=None: search_response)
    monkeypatch.setattr(
        "sonar.service_api.extract_document_record",
        lambda request, transport=None: extracts[request.url],
    )

    response = prepare_paper_set(
        PreparePaperSetRequest(
            query="tool use",
            config_path="config/sonar.example.toml",
            db_path=str(tmp_path / "sonar.sqlite"),
            count=3,
        )
    )

    assert response.selected_count == 3
    assert [source.document_id for source in response.sources] == ["doc-1", "doc-2", "doc-3"]
    assert response.sources[0].authors == ["Alice Example", "Bob Example"]
    assert response.sources[1].authors == ["Carol Example", "Dan Example"]
    assert response.sources[2].summary == "First paragraph of extracted paper text for testing summaries."
    assert any("skipped PDF-only candidate" in warning for warning in response.warnings)


def test_collect_sources_for_topic_maps_to_prepared_set(monkeypatch):
    prepared = PreparePaperSetResponse(
        query="graph retrieval",
        profile="scientific",
        direct_only=True,
        requested_count=1,
        selected_count=1,
        partial_results=False,
        sources=[
            {
                "title": "Graph retrieval paper",
                "url": "https://arxiv.org/abs/2402.00001",
                "selection_reason": "direct paper page",
                "confidence": 0.9,
                "source_type": "paper_landing_page",
                "search_score": 1.2,
                "search_snippet": "paper",
            }
        ],
    )

    monkeypatch.setattr("sonar.service_api.prepare_paper_set", lambda request, transport=None: prepared)

    response = collect_sources_for_topic(
        CollectSourcesForTopicRequest(
            topic="graph retrieval",
            max_results=1,
        )
    )

    assert response.topic == "graph retrieval"
    assert response.corpus == "papers"
    assert response.sources[0].title == "Graph retrieval paper"
