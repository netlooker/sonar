import hashlib
import json
import io
import zipfile
from pathlib import Path

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
    PreparedBundleSource,
    PreparedSourceBundle,
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
    assert first.source_format == "html"
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

    def fake_extract(body: bytes, *, url: str, content_type: str | None = None):
        return type(
            "Extracted",
            (),
            {
                "title": "Example",
                "byline": None,
                "published_at": None,
                "language": "en",
                "excerpt": "Page",
                "abstract": None,
                "text": "Page body",
                "word_count": 2,
                "source_format": "html",
                "extraction_method": "html",
                "extraction_status": "partial",
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
    assert first.extraction_method == "html"
    assert second.from_cache is True
    assert second.text == "Page body"


def test_extract_document_supports_plain_text(tmp_path):
    response = extract_document_record(
        ExtractRequest(
            url="https://example.com/paper.txt",
            config_path="config/sonar.example.toml",
            db_path=str(tmp_path / "sonar.sqlite"),
        ),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="User-agent: *\nAllow: /\n")
            if request.url.path == "/robots.txt"
            else httpx.Response(
                200,
                text="Title line\n\nAbstract\nThis is the abstract.\n\nMain body text.",
                headers={"content-type": "text/plain"},
            )
        ),
    )

    assert response.source_format == "text"
    assert response.extraction_method == "text"
    assert "Main body text" in response.text


def test_extract_document_supports_docx(tmp_path):
    document_bytes = _build_zip_document(
        "word/document.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>Docx Title</w:t></w:r></w:p>
            <w:p><w:r><w:t>Abstract</w:t></w:r></w:p>
            <w:p><w:r><w:t>Structured document body.</w:t></w:r></w:p>
          </w:body>
        </w:document>""",
    )

    response = extract_document_record(
        ExtractRequest(
            url="https://example.com/paper.docx",
            config_path="config/sonar.example.toml",
            db_path=str(tmp_path / "sonar.sqlite"),
        ),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="User-agent: *\nAllow: /\n")
            if request.url.path == "/robots.txt"
            else httpx.Response(
                200,
                content=document_bytes,
                headers={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
            )
        ),
    )

    assert response.source_format == "docx"
    assert response.extraction_method == "docx"
    assert "Structured document body." in response.text


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


def test_prepare_paper_set_persists_bundle_and_merges_html_with_pdf(monkeypatch, tmp_path):
    search_response = SearchResponse(
        query="tool use",
        variants=["tool use"],
        run_id="run-2",
        partial_results=False,
        results=[
            SearchResult(
                title="Tool use with agents",
                url="https://arxiv.org/abs/2401.00002",
                canonical_url="https://arxiv.org/abs/2401.00002",
                snippet="research abstract",
                engine="ddg",
                position=1,
                domain="arxiv.org",
                score=1.0,
            )
        ],
    )
    extracts = {
        "https://arxiv.org/abs/2401.00002": ExtractResponse(
            document_id="doc-landing",
            canonical_url="https://arxiv.org/abs/2401.00002",
            title="Tool use with agents",
            byline="Alice Example, Bob Example",
            published_at="2024-01-10",
            excerpt="Abstract one",
            abstract="Abstract one",
            text="Short landing-page body",
            word_count=3,
            content_type="text/html",
            source_format="html",
            extraction_method="html",
            extraction_status="partial",
            from_cache=False,
        ),
        "https://arxiv.org/pdf/2401.00002.pdf": ExtractResponse(
            document_id="doc-pdf",
            canonical_url="https://arxiv.org/pdf/2401.00002.pdf",
            title="Tool use with agents PDF",
            byline="Alice Example, Bob Example",
            published_at="2024-01-10",
            excerpt="PDF excerpt",
            abstract="PDF abstract",
            text="Full PDF text with much richer extracted content for downstream indexing.",
            word_count=11,
            content_type="application/pdf",
            source_format="pdf",
            extraction_method="pdf",
            extraction_status="full",
            from_cache=True,
        ),
    }

    monkeypatch.setattr("sonar.service_api.search_web", lambda request, transport=None: search_response)
    monkeypatch.setattr("sonar.service_api.extract_document_record", lambda request, transport=None: extracts[request.url])

    response = prepare_paper_set(
        PreparePaperSetRequest(
            query="tool use",
            config_path="config/sonar.example.toml",
            db_path=str(tmp_path / "sonar.sqlite"),
            count=1,
            output_dir=str(tmp_path / "bundles"),
        )
    )

    manifest = Path(response.bundle.bundle_path) / "prepared_source_bundle.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    source = response.bundle.sources[0]

    assert response.selected_count == 1
    assert response.sources[0].source_id == source.source_id
    assert response.bundle.search_run_id == "run-2"
    assert manifest.exists()
    assert payload["artifact_type"] == "prepared_source_bundle"
    assert payload["bundle_version"] == 1
    assert set(payload["sources"][0]).issuperset(
        {
            "source_id",
            "title",
            "origin_url",
            "direct_paper_url",
            "authors",
            "published",
            "summary",
            "abstract",
            "full_text",
            "full_text_path",
            "source_type",
            "retrieved_at",
            "extraction_status",
            "extraction_method",
        }
    )
    assert source.extraction_method == "html+pdf"
    assert source.direct_paper_url == "https://arxiv.org/pdf/2401.00002.pdf"
    assert source.full_text_path is not None
    assert Path(source.full_text_path).exists()


def test_prepare_paper_set_includes_direct_pdf_candidate(monkeypatch, tmp_path):
    search_response = SearchResponse(
        query="tool use",
        variants=["tool use"],
        run_id="run-3",
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
            )
        ],
    )
    extracts = {
        "https://arxiv.org/pdf/2401.00001.pdf": ExtractResponse(
            document_id="doc-pdf",
            canonical_url="https://arxiv.org/pdf/2401.00001.pdf",
            title="Tool Use Paper PDF",
            byline="Alice Example",
            published_at="2024-01-11",
            excerpt="PDF abstract",
            abstract="PDF abstract",
            text="Full PDF body",
            word_count=3,
            content_type="application/pdf",
            source_format="pdf",
            extraction_method="pdf",
            extraction_status="partial",
            from_cache=False,
        )
    }

    monkeypatch.setattr("sonar.service_api.search_web", lambda request, transport=None: search_response)
    monkeypatch.setattr("sonar.service_api.extract_document_record", lambda request, transport=None: extracts[request.url])

    response = prepare_paper_set(
        PreparePaperSetRequest(
            query="tool use",
            config_path="config/sonar.example.toml",
            db_path=str(tmp_path / "sonar.sqlite"),
            count=1,
            persist=False,
        )
    )

    assert response.selected_count == 1
    assert response.sources[0].source_type == "paper_pdf"
    assert not any("skipped PDF-only candidate" in warning for warning in response.warnings)


def test_prepare_paper_set_accepts_direct_docx_candidate(monkeypatch, tmp_path):
    search_response = SearchResponse(
        query="agent memory",
        variants=["agent memory"],
        run_id="run-4",
        partial_results=False,
        results=[
            SearchResult(
                title="Agent memory DOCX",
                url="https://example.com/agent-memory.docx",
                canonical_url="https://example.com/agent-memory.docx",
                snippet="research draft",
                engine="ddg",
                position=1,
                domain="example.com",
                score=1.2,
            )
        ],
    )
    extracts = {
        "https://example.com/agent-memory.docx": ExtractResponse(
            document_id="doc-docx",
            canonical_url="https://example.com/agent-memory.docx",
            title="Agent memory DOCX",
            byline=None,
            published_at=None,
            excerpt="DOCX excerpt",
            abstract=None,
            text="Document body",
            word_count=2,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            source_format="docx",
            extraction_method="docx",
            extraction_status="partial",
            from_cache=False,
        )
    }

    monkeypatch.setattr("sonar.service_api.search_web", lambda request, transport=None: search_response)
    monkeypatch.setattr("sonar.service_api.extract_document_record", lambda request, transport=None: extracts[request.url])

    response = prepare_paper_set(
        PreparePaperSetRequest(
            query="agent memory",
            config_path="config/sonar.example.toml",
            db_path=str(tmp_path / "sonar.sqlite"),
            count=1,
            persist=False,
        )
    )

    assert response.selected_count == 1
    assert response.sources[0].source_type == "paper_docx"
    assert response.sources[0].extraction_method == "docx"


def test_collect_sources_for_topic_maps_to_prepared_set(monkeypatch):
    bundle = PreparedSourceBundle(
        bundle_id="bundle-1",
        created_at=1.0,
        request_fingerprint="fingerprint",
        query="graph retrieval",
        corpus="papers",
        profile="scientific",
        direct_only=True,
        requested_count=1,
        selected_count=1,
        partial_results=False,
        warnings=[],
        search_run_id="run-1",
        sources=[
            PreparedBundleSource(
                source_id="source-1",
                title="Graph retrieval paper",
                origin_url="https://arxiv.org/abs/2402.00001",
                url="https://arxiv.org/abs/2402.00001",
                selection_reason="direct paper page",
                confidence=0.9,
                source_type="paper_landing_page",
                search_score=1.2,
                search_snippet="paper",
                retrieved_at=1.0,
            )
        ],
    )
    prepared = PreparePaperSetResponse(
        query="graph retrieval",
        profile="scientific",
        direct_only=True,
        requested_count=1,
        selected_count=1,
        partial_results=False,
        warnings=[],
        sources=[PreparedBundleSource.model_validate(bundle.sources[0].model_dump())],
        bundle=bundle,
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
    assert response.bundle.bundle_id == "bundle-1"
    assert response.sources[0].title == "Graph retrieval paper"


def _build_zip_document(member: str, content: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member, content)
    return buffer.getvalue()
