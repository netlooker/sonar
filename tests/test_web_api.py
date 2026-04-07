import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from sonar.errors import SonarForbiddenError
from sonar.service_api import (
    PreparePaperSetResponse,
    PreparedBundleSource,
    PreparedSourceBundle,
    SearchResponse,
    SearchResult,
)
from sonar.web_api import create_app


def test_openapi_exposes_sonar_routes():
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["info"]["title"] == "Sonar API"
    assert "/search" in payload["paths"]
    assert "/fetch" in payload["paths"]
    assert "/extract" in payload["paths"]
    assert "/find-papers" in payload["paths"]
    assert "/prepare-paper-set" in payload["paths"]
    assert "/collect-sources" in payload["paths"]


def test_health_endpoint_reports_runtime(tmp_path):
    client = TestClient(create_app())

    response = client.get("/health", params={"config_path": "config/sonar.example.toml", "db_path": str(tmp_path / "sonar.sqlite")})

    assert response.status_code == 200
    assert response.json()["database_path"] == str(tmp_path / "sonar.sqlite")


def test_search_endpoint_uses_shared_service(monkeypatch):
    expected = SearchResponse(
        query="signal",
        variants=["signal"],
        run_id="run-1",
        partial_results=False,
        results=[
            SearchResult(
                title="Result",
                url="https://example.com",
                canonical_url="https://example.com/",
                snippet="snippet",
                engine="ddg",
                position=1,
                domain="example.com",
                score=1.0,
            )
        ],
    )

    monkeypatch.setattr("sonar.web_api.search_web", lambda request: expected)
    client = TestClient(create_app())

    response = client.post("/search", json={"query": "signal"})

    assert response.status_code == 200
    assert response.json()["results"][0]["title"] == "Result"


def test_fetch_endpoint_maps_structured_error(monkeypatch):
    def fail(request):
        raise SonarForbiddenError("robots.txt disallows access")

    monkeypatch.setattr("sonar.web_api.fetch_document_record", fail)
    client = TestClient(create_app())

    response = client.post("/fetch", json={"url": "https://example.com"})

    assert response.status_code == 403
    assert response.json()["detail"]["error_type"] == "forbidden"


def test_prepare_paper_set_endpoint_uses_shared_service(monkeypatch):
    bundle = PreparedSourceBundle(
        bundle_id="bundle-1",
        created_at=1.0,
        request_fingerprint="fingerprint",
        query="agent memory",
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
                title="Agent memory paper",
                origin_url="https://arxiv.org/abs/2401.00001",
                url="https://arxiv.org/abs/2401.00001",
                selection_reason="direct paper page",
                confidence=0.91,
                source_type="paper_landing_page",
                search_score=1.0,
                search_snippet="paper",
                retrieved_at=1.0,
            )
        ],
    )
    expected = PreparePaperSetResponse(
        query="agent memory",
        profile="scientific",
        direct_only=True,
        requested_count=1,
        selected_count=1,
        partial_results=False,
        warnings=[],
        sources=[PreparedBundleSource.model_validate(bundle.sources[0].model_dump())],
        bundle=bundle,
    )

    monkeypatch.setattr("sonar.web_api.prepare_paper_set", lambda request: expected)
    client = TestClient(create_app())

    response = client.post("/prepare-paper-set", json={"query": "agent memory"})

    assert response.status_code == 200
    assert response.json()["sources"][0]["title"] == "Agent memory paper"
    assert response.json()["bundle"]["bundle_id"] == "bundle-1"
