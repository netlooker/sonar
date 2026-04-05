"""Minimal MCP server wrapper for Sonar."""

from __future__ import annotations

import os
from typing import Any

from .errors import SonarError
from .service_api import (
    ExtractRequest,
    FetchRequest,
    HealthRequest,
    SearchRequest,
    extract_document_record,
    fetch_document_record,
    runtime_requirements as service_runtime_requirements,
    search_web,
)
from .settings import load_settings


def runtime_requirements(config_path: str | None = None, db_path: str | None = None) -> dict[str, Any]:
    return service_runtime_requirements(HealthRequest(config_path=config_path, db_path=db_path)).model_dump()


def build_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - installation path
        raise RuntimeError("MCP support is not installed. Install Sonar with the 'mcp' extra.") from exc

    mcp = FastMCP(
        "Sonar",
        instructions=(
            "Use Sonar for deterministic live-web evidence. Prefer explicit search, fetch, and extract steps."
        ),
        json_response=True,
    )

    @mcp.tool(name="sonar_health", description="Report Sonar runtime requirements and readiness")
    def sonar_health(config_path: str | None = None, db_path: str | None = None) -> dict[str, Any]:
        return runtime_requirements(config_path=config_path, db_path=db_path)

    @mcp.tool(name="sonar_search", description="Search the live web through SearxNG and return ranked evidence")
    def sonar_search(
        query: str,
        config_path: str | None = None,
        db_path: str | None = None,
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
                config_path=config_path,
                db_path=db_path,
                limit=limit,
                engines=engines,
                categories=categories,
                language=language,
                freshness=freshness,
                force_refresh=force_refresh,
            )
        ).model_dump()

    @mcp.tool(name="sonar_fetch", description="Fetch one URL and cache its metadata")
    def sonar_fetch(
        url: str,
        config_path: str | None = None,
        db_path: str | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        return fetch_document_record(
            FetchRequest(
                url=url,
                config_path=config_path,
                db_path=db_path,
                force_refresh=force_refresh,
            )
        ).model_dump()

    @mcp.tool(name="sonar_extract", description="Extract readable text from one cached or live URL")
    def sonar_extract(
        url: str | None = None,
        document_id: str | None = None,
        config_path: str | None = None,
        db_path: str | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        return extract_document_record(
            ExtractRequest(
                url=url,
                document_id=document_id,
                config_path=config_path,
                db_path=db_path,
                force_refresh=force_refresh,
            )
        ).model_dump()

    return mcp


def main() -> None:
    _require_server_config()
    transport = os.environ.get("SONAR_MCP_TRANSPORT", "stdio")
    build_server().run(transport=transport)


def _require_server_config() -> None:
    config_path = os.environ.get("SONAR_CONFIG")
    if not config_path:
        raise RuntimeError("SONAR_CONFIG is required when starting sonar-mcp.")
    load_settings(config_path)


def map_mcp_error(exc: SonarError) -> RuntimeError:
    return RuntimeError(str(exc.to_dict()))
