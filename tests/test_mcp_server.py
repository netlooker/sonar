import json
from pathlib import Path

import pytest

mcp = pytest.importorskip("mcp")

from sonar.mcp_server import _require_server_config, build_server, runtime_requirements  # noqa: E402
from sonar.service_api import (  # noqa: E402
    CollectSourcesForTopicResponse,
    ExtractResponse,
    FindPapersResponse,
    PreparePaperSetResponse,
    PreparedSourceBundle,
)


def test_runtime_requirements_reports_database_path(tmp_path):
    response = runtime_requirements(
        config_path="config/sonar.example.toml", db_path=str(tmp_path / "sonar.sqlite")
    )

    assert response["database_path"] == str(tmp_path / "sonar.sqlite")


def test_build_server_lists_expected_tools():
    server = build_server()
    tool_names = set(server._tool_manager._tools.keys())

    assert tool_names == {
        "health",
        "search",
        "fetch",
        "extract",
        "scrape",
        "find_papers",
        "prepare_paper_set",
        "collect_sources_for_topic",
    }


def test_build_server_applies_streamable_http_settings():
    server = build_server(
        host="0.0.0.0",
        port=8123,
        path="/custom-mcp",
        stateless_http=False,
    )

    assert server.settings.host == "0.0.0.0"
    assert server.settings.port == 8123
    assert server.settings.streamable_http_path == "/custom-mcp"
    assert server.settings.stateless_http is False


def test_mcp_tool_descriptions_reflect_pdf_and_topic_filtering():
    server = build_server()
    tools = server._tool_manager._tools

    assert "known URL" in tools["scrape"].description
    assert (
        "semantic relevance pruning" in tools["collect_sources_for_topic"].description
    )


def test_mcp_tool_schemas_hide_operator_only_paths():
    server = build_server()
    forbidden = {"config_path", "db_path", "output_dir"}

    for tool in server._tool_manager._tools.values():
        assert forbidden.isdisjoint(tool.parameters.get("properties", {}))


def test_example_mcp_config_is_valid_json():
    payload = json.loads(
        Path("config/sonar.mcp.example.json").read_text(encoding="utf-8")
    )

    assert "mcpServers" in payload
    assert payload["mcpServers"]["sonar"]["env"]["SONAR_MCP_TRANSPORT"] == "stdio"


def test_mcp_entrypoint_requires_config(monkeypatch):
    monkeypatch.delenv("SONAR_CONFIG", raising=False)

    with pytest.raises(RuntimeError, match="SONAR_CONFIG is required"):
        _require_server_config()


def test_health_tool_uses_configured_runtime(monkeypatch):
    monkeypatch.setenv("SONAR_CONFIG", "config/sonar.example.toml")
    server = build_server()
    result = server._tool_manager._tools["health"].fn()

    assert result["database_path"].endswith(".sonar/sonar.sqlite")


def test_extract_tool_wraps_pdf_capable_service(monkeypatch):
    server = build_server()
    captured = {}

    def fake_extract_document_record(request):
        captured["request"] = request
        return ExtractResponse(
            document_id="doc-pdf",
            canonical_url="https://example.com/paper.pdf",
            title="PDF Paper",
            byline="Alice Example",
            excerpt="PDF excerpt",
            abstract="PDF abstract",
            text="Full PDF text",
            word_count=3,
            content_type="application/pdf",
            source_format="pdf",
            extraction_method="pdf",
            extraction_status="full",
            from_cache=False,
        )

    monkeypatch.setattr(
        "sonar.mcp_server.extract_document_record", fake_extract_document_record
    )

    result = server._tool_manager._tools["extract"].fn(
        url="https://example.com/paper.pdf", force_refresh=True
    )

    assert captured["request"].url == "https://example.com/paper.pdf"
    assert captured["request"].force_refresh is True
    assert result["source_format"] == "pdf"
    assert result["extraction_method"] == "pdf"
    assert result["text"] == "Full PDF text"


def test_extract_tool_compacts_text_without_changing_word_count(monkeypatch):
    server = build_server()
    monkeypatch.setattr(
        "sonar.mcp_server.extract_document_record",
        lambda request: ExtractResponse(
            document_id="doc",
            canonical_url="https://example.com",
            text="abcdefghij",
            word_count=1,
            from_cache=False,
        ),
    )

    result = server._tool_manager._tools["extract"].fn(
        url="https://example.com", max_chars=4
    )

    assert result["text"] == "abcd\n...[truncated]"
    assert result["word_count"] == 1
    assert "mcp_text_truncated" in result["retrieval_warnings"]


def test_scrape_tool_requires_url_and_reuses_extract_service(monkeypatch):
    server = build_server()
    captured = {}

    def fake_extract_document_record(request):
        captured["request"] = request
        return ExtractResponse(
            document_id="doc",
            canonical_url=request.url,
            text="scraped text",
            word_count=2,
            retrieval_backend="cloakbrowser",
            rendered=True,
            from_cache=False,
        )

    monkeypatch.setattr(
        "sonar.mcp_server.extract_document_record", fake_extract_document_record
    )

    tool = server._tool_manager._tools["scrape"]
    result = tool.fn(url="https://example.com/app", force_refresh=True)

    assert set(tool.parameters["required"]) == {"url"}
    assert captured["request"].url == "https://example.com/app"
    assert captured["request"].document_id is None
    assert captured["request"].force_refresh is True
    assert result["text"] == "scraped text"
    assert result["retrieval_backend"] == "cloakbrowser"
    assert result["rendered"] is True


def test_unprefixed_paper_tools_call_service_functions(monkeypatch):
    server = build_server()
    calls = []

    def fake_find(request):
        calls.append(("find", request.query))
        return FindPapersResponse(
            query=request.query,
            profile=request.profile,
            direct_only=request.direct_only,
            partial_results=False,
            candidates=[],
        )

    def fake_prepare(request):
        calls.append(("prepare", request.query))
        bundle = PreparedSourceBundle(
            bundle_id="bundle-empty",
            created_at=1.0,
            request_fingerprint="fingerprint",
            query=request.query,
            corpus="papers",
            profile=request.profile,
            direct_only=request.direct_only,
            requested_count=request.count,
            selected_count=0,
            partial_results=True,
            sources=[],
        )
        return PreparePaperSetResponse(
            query=request.query,
            profile=request.profile,
            direct_only=request.direct_only,
            requested_count=request.count,
            selected_count=0,
            partial_results=True,
            sources=[],
            bundle=bundle,
        )

    monkeypatch.setattr("sonar.mcp_server.service_find_papers", fake_find)
    monkeypatch.setattr("sonar.mcp_server.service_prepare_paper_set", fake_prepare)

    find_result = server._tool_manager._tools["find_papers"].fn(query="retrieval")
    prepare_result = server._tool_manager._tools["prepare_paper_set"].fn(
        query="retrieval", persist=False
    )

    assert calls == [("find", "retrieval"), ("prepare", "retrieval")]
    assert find_result["query"] == "retrieval"
    assert prepare_result["query"] == "retrieval"


def test_collect_sources_tool_wraps_semantic_topic_collection(monkeypatch):
    server = build_server()
    captured = {}

    def fake_collect_sources_for_topic(request):
        captured["request"] = request
        return CollectSourcesForTopicResponse(
            topic=request.topic,
            corpus=request.corpus,
            profile=request.profile,
            direct_only=request.direct_only,
            requested_count=request.max_results,
            selected_count=1,
            partial_results=True,
            warnings=["filtered out 1 low-relevance sources for topic search."],
            sources=[],
            bundle=PreparedSourceBundle(
                bundle_id="bundle-1",
                created_at=1.0,
                request_fingerprint="fingerprint",
                query=request.topic,
                corpus=request.corpus,
                profile=request.profile,
                direct_only=request.direct_only,
                requested_count=request.max_results,
                selected_count=1,
                partial_results=True,
                warnings=["filtered out 1 low-relevance sources for topic search."],
                search_run_id="run-1",
                sources=[],
            ),
        )

    monkeypatch.setattr(
        "sonar.mcp_server.collect_sources_for_topic", fake_collect_sources_for_topic
    )

    result = server._tool_manager._tools["collect_sources_for_topic"].fn(
        topic="llm prompting",
        max_results=2,
        persist=False,
    )

    assert captured["request"].topic == "llm prompting"
    assert captured["request"].max_results == 2
    assert captured["request"].persist is False
    assert result["selected_count"] == 1
    assert "low-relevance sources" in result["warnings"][0]
