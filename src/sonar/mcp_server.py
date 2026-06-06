"""Minimal MCP server wrapper for Sonar."""

from __future__ import annotations

import os
from typing import Any

from .errors import SonarError
from .service_api import (
    CollectSourcesForTopicRequest,
    ExtractRequest,
    FetchRequest,
    FindPapersRequest,
    HealthRequest,
    PreparePaperSetRequest,
    SearchRequest,
    collect_sources_for_topic,
    extract_document_record,
    fetch_document_record,
    find_papers as service_find_papers,
    prepare_paper_set as service_prepare_paper_set,
    runtime_requirements as service_runtime_requirements,
    search_web,
)
from .settings import load_settings


def runtime_requirements(
    config_path: str | None = None, db_path: str | None = None
) -> dict[str, Any]:
    return service_runtime_requirements(
        HealthRequest(config_path=config_path, db_path=db_path)
    ).model_dump()


MAX_MCP_TEXT_CHARS = 50_000
DEFAULT_MCP_TEXT_CHARS = 12_000


def build_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    path: str = "/mcp",
    stateless_http: bool = True,
):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - installation path
        raise RuntimeError(
            "MCP support is not installed. Install Sonar with the 'mcp' extra."
        ) from exc

    mcp = FastMCP(
        "Sonar",
        instructions=(
            "Use Sonar for deterministic live-web evidence. Normally search, "
            "then extract only selected URLs; extract does not require a prior "
            "fetch. Use fetch only for metadata probes. Use paper-preparation "
            "tools when fewer transitions and durable prepared-source bundles "
            "are useful."
        ),
        host=host,
        port=port,
        streamable_http_path=path,
        stateless_http=stateless_http,
        json_response=True,
    )

    @mcp.tool(
        name="health",
        description="Report Sonar runtime readiness; use for diagnostics, not normal research",
    )
    def health() -> dict[str, Any]:
        return runtime_requirements()

    @mcp.tool(
        name="search",
        description="Discover ranked candidate URLs through SearxNG; extract only selected results",
    )
    def search(
        query: str,
        limit: int | None = None,
        engines: list[str] | None = None,
        categories: list[str] | None = None,
        language: str | None = None,
        freshness: str = "any",
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        return search_web(
            SearchRequest(
                query=query,
                limit=limit,
                engines=engines,
                categories=categories,
                language=language,
                freshness=freshness,
                force_refresh=force_refresh,
            )
        ).model_dump()

    @mcp.tool(
        name="fetch",
        description="Probe and cache URL metadata; usually call extract directly instead",
    )
    def fetch(
        url: str,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        return fetch_document_record(
            FetchRequest(
                url=url,
                force_refresh=force_refresh,
            )
        ).model_dump()

    @mcp.tool(
        name="extract",
        description="Retrieve and extract readable HTML, PDF, and document content; no prior fetch call is required",
    )
    def extract(
        url: str | None = None,
        document_id: str | None = None,
        force_refresh: bool = False,
        include_text: bool = True,
        max_chars: int = DEFAULT_MCP_TEXT_CHARS,
    ) -> dict[str, Any]:
        response = extract_document_record(
            ExtractRequest(
                url=url,
                document_id=document_id,
                force_refresh=force_refresh,
            )
        )
        return _compact_extract_response(
            response.model_dump(), include_text=include_text, max_chars=max_chars
        )

    @mcp.tool(
        name="find_papers",
        description="Discover curated scientific paper candidates without extracting every result",
    )
    def find_papers(
        query: str,
        count: int = 5,
        profile: str = "scientific",
        direct_only: bool = True,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        return service_find_papers(
            FindPapersRequest(
                query=query,
                count=count,
                profile=profile,
                direct_only=direct_only,
                force_refresh=force_refresh,
            )
        ).model_dump()

    @mcp.tool(
        name="prepare_paper_set",
        description="Search, filter, extract, and persist a scientific paper set in one call",
    )
    def prepare_paper_set(
        query: str,
        count: int = 5,
        profile: str = "scientific",
        direct_only: bool = True,
        force_refresh: bool = False,
        include_full_text: bool = True,
        persist: bool = True,
        include_sidecars: bool = True,
    ) -> dict[str, Any]:
        return service_prepare_paper_set(
            PreparePaperSetRequest(
                query=query,
                count=count,
                profile=profile,
                direct_only=direct_only,
                force_refresh=force_refresh,
                include_full_text=include_full_text,
                persist=persist,
                include_sidecars=include_sidecars,
            )
        ).model_dump()

    @mcp.tool(
        name="collect_sources_for_topic",
        description="Collect, extract, apply semantic relevance pruning, and persist a compact source bundle for a topic",
    )
    def collect_sources_for_topic_tool(
        topic: str,
        max_results: int = 5,
        corpus: str = "papers",
        profile: str = "scientific",
        direct_only: bool = True,
        force_refresh: bool = False,
        include_full_text: bool = True,
        persist: bool = True,
        include_sidecars: bool = True,
    ) -> dict[str, Any]:
        return collect_sources_for_topic(
            CollectSourcesForTopicRequest(
                topic=topic,
                max_results=max_results,
                corpus=corpus,
                profile=profile,
                direct_only=direct_only,
                force_refresh=force_refresh,
                include_full_text=include_full_text,
                persist=persist,
                include_sidecars=include_sidecars,
            )
        ).model_dump()

    return mcp


def main() -> None:
    _require_server_config()
    transport = os.environ.get("SONAR_MCP_TRANSPORT", "stdio")
    build_server(
        host=os.environ.get("SONAR_MCP_HOST", "127.0.0.1"),
        port=int(os.environ.get("SONAR_MCP_PORT", "8000")),
        path=os.environ.get("SONAR_MCP_PATH", "/mcp"),
        stateless_http=_env_bool("SONAR_MCP_STATELESS_HTTP", True),
    ).run(transport=transport)


def _require_server_config() -> None:
    config_path = os.environ.get("SONAR_CONFIG")
    if not config_path:
        raise RuntimeError("SONAR_CONFIG is required when starting sonar-mcp.")
    load_settings(config_path)


def map_mcp_error(exc: SonarError) -> RuntimeError:
    return RuntimeError(str(exc.to_dict()))


def _compact_extract_response(
    payload: dict[str, Any], *, include_text: bool, max_chars: int
) -> dict[str, Any]:
    result = dict(payload)
    warnings = list(result.get("retrieval_warnings", []))
    limit = max(0, min(max_chars, MAX_MCP_TEXT_CHARS))
    if max_chars > MAX_MCP_TEXT_CHARS:
        warnings.append(f"mcp_max_chars_clamped_to_{MAX_MCP_TEXT_CHARS}")
    text = str(result.get("text", ""))
    if not include_text:
        result.pop("text", None)
    elif len(text) > limit:
        result["text"] = text[:limit] + "\n...[truncated]"
        warnings.append("mcp_text_truncated")
    result["retrieval_warnings"] = list(dict.fromkeys(warnings))
    return result


def _env_bool(name: str, default: bool) -> bool:
    return str(os.environ.get(name, default)).lower() not in {"0", "false", "no", "off"}
