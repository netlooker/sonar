"""Shared runtime service layer for Sonar transports."""

from __future__ import annotations

import hashlib
from pathlib import Path
from time import time
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field

from .errors import SonarBadRequestError, SonarNotFoundError, SonarUpstreamUnavailableError
from .extract import extract_document, trafilatura_available
from .fetch import fetch_url
from .query_planner import generate_query_variants, normalize_query
from .ranking import canonicalize_url, dedupe_results, query_signature, rank_results, url_domain
from .search_providers import SearxNGProvider
from .settings import AppSettings, load_settings
from .storage import Repository


class RequirementSummary(BaseModel):
    python_environment: bool = True
    writable_database_parent: bool
    searxng_configured: bool
    trafilatura_installed: bool


class HealthRequest(BaseModel):
    config_path: str | None = None
    db_path: str | None = None


class HealthResponse(BaseModel):
    config_path: str | None = None
    database_path: str
    database_exists: bool
    searxng_base_url: str
    http_host: str
    http_port: int
    requirements: RequirementSummary
    ready: bool


class SearchRequest(BaseModel):
    query: str
    config_path: str | None = None
    db_path: str | None = None
    limit: int | None = None
    engines: list[str] | None = None
    categories: list[str] | None = None
    language: str | None = None
    freshness: str = "any"
    force_refresh: bool = False


class SearchResult(BaseModel):
    title: str
    url: str
    canonical_url: str
    snippet: str
    engine: str
    position: int
    domain: str
    published_at: str | None = None
    score: float


class SearchResponse(BaseModel):
    query: str
    variants: list[str]
    run_id: str
    partial_results: bool
    warnings: list[str] = Field(default_factory=list)
    results: list[SearchResult] = Field(default_factory=list)
    from_cache: bool = False


class FetchRequest(BaseModel):
    url: str
    config_path: str | None = None
    db_path: str | None = None
    force_refresh: bool = False


class FetchResponse(BaseModel):
    document_id: str
    url: str
    final_url: str
    status: str
    status_code: int
    content_type: str
    fetched_at: float
    from_cache: bool


class ExtractRequest(BaseModel):
    url: str | None = None
    document_id: str | None = None
    config_path: str | None = None
    db_path: str | None = None
    force_refresh: bool = False


class ExtractResponse(BaseModel):
    document_id: str
    canonical_url: str
    title: str | None = None
    byline: str | None = None
    published_at: str | None = None
    language: str | None = None
    excerpt: str | None = None
    text: str
    word_count: int
    from_cache: bool


def resolve_runtime(config_path: str | None = None, db_path: str | None = None) -> tuple[AppSettings, Path]:
    settings = load_settings(config_path)
    path = Path(db_path or settings.database.path).expanduser()
    return settings, path


def runtime_requirements(request: HealthRequest) -> HealthResponse:
    settings, db_path = resolve_runtime(request.config_path, request.db_path)
    writable_database_parent = db_path.parent.exists() and db_path.parent.is_dir()
    return HealthResponse(
        config_path=str(settings.config_path) if settings.config_path else None,
        database_path=str(db_path),
        database_exists=db_path.exists(),
        searxng_base_url=settings.searxng.base_url,
        http_host=settings.http.host,
        http_port=settings.http.port,
        requirements=RequirementSummary(
            writable_database_parent=writable_database_parent,
            searxng_configured=bool(settings.searxng.base_url),
            trafilatura_installed=trafilatura_available(),
        ),
        ready=writable_database_parent and bool(settings.searxng.base_url),
    )


def search_web(request: SearchRequest, *, transport: httpx.BaseTransport | None = None) -> SearchResponse:
    settings, db_path = resolve_runtime(request.config_path, request.db_path)
    normalized_query = normalize_query(request.query)
    if not normalized_query:
        raise SonarBadRequestError("Search query must not be empty.")

    limit = request.limit or settings.search.default_limit
    if limit < 1 or limit > settings.search.max_limit:
        raise SonarBadRequestError(f"Search limit must be between 1 and {settings.search.max_limit}.")
    if request.freshness not in {"any", "day", "week", "month"}:
        raise SonarBadRequestError("Freshness must be one of: any, day, week, month.")

    repo = Repository(db_path)
    repo.initialize()
    try:
        repo.upsert_domain_priors(settings.domain_priors)
        signature = query_signature(
            normalized_query,
            limit=limit,
            engines=request.engines,
            categories=request.categories,
            language=request.language,
            freshness=request.freshness,
        )
        now = time()
        if not request.force_refresh:
            cached = repo.get_cached_search(signature, now)
            if cached:
                run_row, rows = cached
                return SearchResponse(
                    query=normalized_query,
                    variants=run_row.variants,
                    run_id=run_row.run_id,
                    partial_results=run_row.partial_results,
                    warnings=run_row.warnings,
                    results=[SearchResult.model_validate(row) for row in rows[:limit]],
                    from_cache=True,
                )

        provider = SearxNGProvider(
            base_url=settings.searxng.base_url,
            api_key=settings.searxng.api_key,
            authorization_header=settings.searxng.authorization_header,
            transport=transport,
            timeout=settings.fetch.read_timeout_seconds,
        )
        variants = generate_query_variants(normalized_query)
        warnings: list[str] = []
        raw_results: list[dict[str, object]] = []
        partial_results = False

        for variant in variants:
            try:
                variant_results = provider.search(
                    variant,
                    engines=request.engines,
                    categories=request.categories,
                    language=request.language,
                    freshness=request.freshness,
                )
            except Exception as exc:
                warnings.append(f"variant failed: {variant}: {exc}")
                partial_results = True
                continue
            for item in variant_results:
                raw_results.append(
                    {
                        "title": item.title,
                        "url": item.url,
                        "canonical_url": canonicalize_url(item.url),
                        "snippet": item.snippet,
                        "engine": item.engine,
                        "position": item.position,
                        "domain": url_domain(canonicalize_url(item.url)),
                        "published_at": item.published_at,
                    }
                )

        if not raw_results and warnings:
            raise SonarUpstreamUnavailableError(warnings[0])

        ranked = rank_results(raw_results, normalized_query, repo.get_domain_priors())
        deduped = dedupe_results(ranked)[:limit]
        run_id = str(uuid4())
        repo.store_search_run(
            signature=signature,
            run_id=run_id,
            query=normalized_query,
            variants=variants,
            partial_results=partial_results,
            warnings=warnings,
            created_at=now,
            expires_at=now + settings.cache.search_ttl_seconds,
            results=deduped,
        )
        return SearchResponse(
            query=normalized_query,
            variants=variants,
            run_id=run_id,
            partial_results=partial_results,
            warnings=warnings,
            results=[SearchResult.model_validate(row) for row in deduped],
            from_cache=False,
        )
    finally:
        repo.close()


def fetch_document_record(request: FetchRequest, *, transport: httpx.BaseTransport | None = None) -> FetchResponse:
    settings, db_path = resolve_runtime(request.config_path, request.db_path)
    canonical_url = canonicalize_url(request.url)
    repo = Repository(db_path)
    repo.initialize()
    try:
        existing = repo.get_document_by_canonical_url(canonical_url)
        now = time()
        if existing is not None and not request.force_refresh and float(existing["fetch_expires_at"]) > now:
            return FetchResponse(
                document_id=str(existing["document_id"]),
                url=str(existing["url"]),
                final_url=str(existing["final_url"]),
                status=str(existing["status"]),
                status_code=int(existing["status_code"]),
                content_type=str(existing["content_type"]),
                fetched_at=float(existing["fetched_at"]),
                from_cache=True,
            )

        artifact = fetch_url(
            url=request.url,
            user_agent=settings.fetch.user_agent,
            connect_timeout_seconds=settings.fetch.connect_timeout_seconds,
            read_timeout_seconds=settings.fetch.read_timeout_seconds,
            max_body_bytes=settings.fetch.max_body_bytes,
            transport=transport,
            include_body=False,
        )
        document_id = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
        repo.store_document_fetch(
            document_id=document_id,
            url=request.url,
            canonical_url=canonical_url,
            final_url=artifact.final_url,
            status=artifact.status,
            status_code=artifact.status_code,
            content_type=artifact.content_type,
            fetched_at=now,
            fetch_expires_at=now + settings.cache.extract_ttl_seconds,
            extractable=artifact.extractable,
        )
        return FetchResponse(
            document_id=document_id,
            url=request.url,
            final_url=artifact.final_url,
            status=artifact.status,
            status_code=artifact.status_code,
            content_type=artifact.content_type,
            fetched_at=now,
            from_cache=False,
        )
    finally:
        repo.close()


def extract_document_record(request: ExtractRequest, *, transport: httpx.BaseTransport | None = None) -> ExtractResponse:
    settings, db_path = resolve_runtime(request.config_path, request.db_path)
    repo = Repository(db_path)
    repo.initialize()
    try:
        now = time()
        row = _resolve_document(repo, request)
        if row is not None and not request.force_refresh and row["text"] and row["extract_expires_at"] and float(row["extract_expires_at"]) > now:
            return ExtractResponse(
                document_id=str(row["document_id"]),
                canonical_url=str(row["canonical_url"]),
                title=row["title"],
                byline=row["byline"],
                published_at=row["published_at"],
                language=row["language"],
                excerpt=row["excerpt"],
                text=str(row["text"]),
                word_count=int(row["word_count"]),
                from_cache=True,
            )

        if request.document_id:
            if row is None:
                raise SonarNotFoundError(f"Unknown document id: {request.document_id}")
            url = str(row["final_url"])
            canonical_url = str(row["canonical_url"])
        elif request.url:
            url = request.url
            canonical_url = canonicalize_url(request.url)
        else:
            raise SonarBadRequestError("Provide either url or document_id.")

        fetched = fetch_url(
            url=url,
            user_agent=settings.fetch.user_agent,
            connect_timeout_seconds=settings.fetch.connect_timeout_seconds,
            read_timeout_seconds=settings.fetch.read_timeout_seconds,
            max_body_bytes=settings.fetch.max_body_bytes,
            transport=transport,
            include_body=True,
        )
        if not fetched.extractable:
            raise SonarBadRequestError("Fetched document is not extractable HTML.")
        document_id = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
        repo.store_document_fetch(
            document_id=document_id,
            url=request.url or str(row["url"]),
            canonical_url=canonical_url,
            final_url=fetched.final_url,
            status=fetched.status,
            status_code=fetched.status_code,
            content_type=fetched.content_type,
            fetched_at=now,
            fetch_expires_at=now + settings.cache.extract_ttl_seconds,
            extractable=True,
        )
        extracted = extract_document(fetched.body or b"", url=fetched.final_url)
        repo.store_extract(
            document_id=document_id,
            title=extracted.title,
            byline=extracted.byline,
            published_at=extracted.published_at,
            language=extracted.language,
            excerpt=extracted.excerpt,
            text=extracted.text,
            word_count=extracted.word_count,
            extract_hash=hashlib.sha256(extracted.text.encode("utf-8")).hexdigest(),
            extract_expires_at=now + settings.cache.extract_ttl_seconds,
        )
        return ExtractResponse(
            document_id=document_id,
            canonical_url=canonical_url,
            title=extracted.title,
            byline=extracted.byline,
            published_at=extracted.published_at,
            language=extracted.language,
            excerpt=extracted.excerpt,
            text=extracted.text,
            word_count=extracted.word_count,
            from_cache=False,
        )
    finally:
        repo.close()


def _resolve_document(repo: Repository, request: ExtractRequest):
    if request.document_id:
        return repo.get_document_by_id(request.document_id)
    if request.url:
        return repo.get_document_by_canonical_url(canonicalize_url(request.url))
    return None
