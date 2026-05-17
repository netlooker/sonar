import json
from pathlib import Path

import pytest

mcp = pytest.importorskip("mcp")

from sonar.mcp_server import _require_server_config, build_server, runtime_requirements
from sonar.service_api import CollectSourcesForTopicResponse, ExtractResponse, PreparedSourceBundle


def test_runtime_requirements_reports_database_path(tmp_path):
    response = runtime_requirements(config_path="config/sonar.example.toml", db_path=str(tmp_path / "sonar.sqlite"))

    assert response["database_path"] == str(tmp_path / "sonar.sqlite")


def test_build_server_lists_expected_tools():
    server = build_server()
    tool_names = set(server._tool_manager._tools.keys())

    assert "sonar_health" in tool_names
    assert "sonar_search" in tool_names
    assert "sonar_fetch" in tool_names
    assert "sonar_extract" in tool_names
    assert "sonar_find_papers" in tool_names
    assert "sonar_prepare_paper_set" in tool_names
    assert "sonar_collect_sources_for_topic" in tool_names


def test_mcp_tool_descriptions_reflect_pdf_and_topic_filtering():
    server = build_server()
    tools = server._tool_manager._tools

    assert "PDF" in tools["sonar_extract"].description
    assert "semantic relevance pruning" in tools["sonar_collect_sources_for_topic"].description


def test_example_mcp_config_is_valid_json():
    payload = json.loads(Path("config/sonar.mcp.example.json").read_text(encoding="utf-8"))

    assert "mcpServers" in payload
    assert payload["mcpServers"]["sonar"]["env"]["SONAR_MCP_TRANSPORT"] == "stdio"


def test_mcp_entrypoint_requires_config(monkeypatch):
    monkeypatch.delenv("SONAR_CONFIG", raising=False)

    with pytest.raises(RuntimeError, match="SONAR_CONFIG is required"):
        _require_server_config()


def test_health_tool_uses_shared_runtime(tmp_path):
    server = build_server()
    result = server._tool_manager._tools["sonar_health"].fn(
        config_path="config/sonar.example.toml",
        db_path=str(tmp_path / "sonar.sqlite"),
    )

    assert result["database_path"] == str(tmp_path / "sonar.sqlite")


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

    monkeypatch.setattr("sonar.mcp_server.extract_document_record", fake_extract_document_record)

    result = server._tool_manager._tools["sonar_extract"].fn(url="https://example.com/paper.pdf", force_refresh=True)

    assert captured["request"].url == "https://example.com/paper.pdf"
    assert captured["request"].force_refresh is True
    assert result["source_format"] == "pdf"
    assert result["extraction_method"] == "pdf"
    assert result["text"] == "Full PDF text"


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

    monkeypatch.setattr("sonar.mcp_server.collect_sources_for_topic", fake_collect_sources_for_topic)

    result = server._tool_manager._tools["sonar_collect_sources_for_topic"].fn(
        topic="llm prompting",
        max_results=2,
        persist=False,
    )

    assert captured["request"].topic == "llm prompting"
    assert captured["request"].max_results == 2
    assert captured["request"].persist is False
    assert result["selected_count"] == 1
    assert "low-relevance sources" in result["warnings"][0]
