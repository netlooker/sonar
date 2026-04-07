"""HTTP/OpenAPI adapter for Sonar."""

from __future__ import annotations

from pydantic import BaseModel

from .errors import SonarError
from .service_api import (
    CollectSourcesForTopicRequest,
    CollectSourcesForTopicResponse,
    ExtractRequest,
    ExtractResponse,
    FetchRequest,
    FetchResponse,
    FindPapersRequest,
    FindPapersResponse,
    HealthRequest,
    HealthResponse,
    PreparePaperSetRequest,
    PreparePaperSetResponse,
    SearchRequest,
    SearchResponse,
    collect_sources_for_topic,
    extract_document_record,
    fetch_document_record,
    find_papers,
    prepare_paper_set,
    runtime_requirements,
    search_web,
)


class ErrorResponse(BaseModel):
    error_type: str
    message: str
    retryable: bool
    dependency: str | None = None
    timeout_seconds: float | None = None


def create_app():
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:  # pragma: no cover - installation path
        raise RuntimeError(
            "FastAPI is not installed. Install Sonar with the 'api' extra, for example: pip install -e '.[api]'"
        ) from exc

    app = FastAPI(
        title="Sonar API",
        summary="HTTP and OpenAPI interface for deterministic live-web evidence.",
        version="0.1.0",
        description="Expose Sonar search, fetch, extract, prepared paper sets, and runtime readiness over JSON/HTTP.",
    )

    def map_error(exc: Exception) -> HTTPException:
        if isinstance(exc, SonarError):
            return HTTPException(status_code=exc.status_code, detail=exc.to_dict())
        if isinstance(exc, FileNotFoundError):
            return HTTPException(status_code=404, detail={"error_type": "not_found", "message": str(exc), "retryable": False})
        if isinstance(exc, ValueError):
            return HTTPException(status_code=400, detail={"error_type": "bad_request", "message": str(exc), "retryable": False})
        return HTTPException(status_code=500, detail={"error_type": "internal_error", "message": str(exc), "retryable": False})

    @app.get("/health", response_model=HealthResponse, tags=["sonar"])
    def get_health(config_path: str | None = None, db_path: str | None = None) -> HealthResponse:
        try:
            return runtime_requirements(HealthRequest(config_path=config_path, db_path=db_path))
        except Exception as exc:  # pragma: no cover
            raise map_error(exc) from exc

    @app.post("/search", response_model=SearchResponse, tags=["sonar"], responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
    def post_search(request: SearchRequest) -> SearchResponse:
        try:
            return search_web(request)
        except Exception as exc:  # pragma: no cover
            raise map_error(exc) from exc

    @app.post("/fetch", response_model=FetchResponse, tags=["sonar"], responses={400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
    def post_fetch(request: FetchRequest) -> FetchResponse:
        try:
            return fetch_document_record(request)
        except Exception as exc:  # pragma: no cover
            raise map_error(exc) from exc

    @app.post("/extract", response_model=ExtractResponse, tags=["sonar"], responses={400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 424: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
    def post_extract(request: ExtractRequest) -> ExtractResponse:
        try:
            return extract_document_record(request)
        except Exception as exc:  # pragma: no cover
            raise map_error(exc) from exc

    @app.post("/find-papers", response_model=FindPapersResponse, tags=["sonar"], responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
    def post_find_papers(request: FindPapersRequest) -> FindPapersResponse:
        try:
            return find_papers(request)
        except Exception as exc:  # pragma: no cover
            raise map_error(exc) from exc

    @app.post("/prepare-paper-set", response_model=PreparePaperSetResponse, tags=["sonar"], responses={400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 424: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
    def post_prepare_paper_set(request: PreparePaperSetRequest) -> PreparePaperSetResponse:
        try:
            return prepare_paper_set(request)
        except Exception as exc:  # pragma: no cover
            raise map_error(exc) from exc

    @app.post("/collect-sources", response_model=CollectSourcesForTopicResponse, tags=["sonar"], responses={400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 424: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
    def post_collect_sources(request: CollectSourcesForTopicRequest) -> CollectSourcesForTopicResponse:
        try:
            return collect_sources_for_topic(request)
        except Exception as exc:  # pragma: no cover
            raise map_error(exc) from exc

    return app


def main() -> None:
    import uvicorn

    from .settings import load_settings

    settings = load_settings()
    uvicorn.run(
        "sonar.web_api:create_app",
        factory=True,
        host=settings.http.host,
        port=settings.http.port,
        reload=False,
    )
