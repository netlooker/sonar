"""Shared runtime service layer for Sonar transports."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from time import time
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field

from .errors import SonarBadRequestError, SonarError, SonarNotFoundError, SonarUpstreamUnavailableError
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


class FindPapersRequest(BaseModel):
    query: str
    config_path: str | None = None
    db_path: str | None = None
    count: int = 5
    profile: str = "scientific"
    direct_only: bool = True
    force_refresh: bool = False


class PreparedSource(BaseModel):
    title: str
    url: str
    published: str | None = None
    authors: list[str] = Field(default_factory=list)
    summary: str | None = None
    full_text: str | None = None
    selection_reason: str
    confidence: float
    source_type: str
    direct_paper_url: str | None = None
    document_id: str | None = None
    search_score: float
    search_snippet: str
    from_search_cache: bool = False
    from_extract_cache: bool = False


class FindPapersResponse(BaseModel):
    query: str
    profile: str
    direct_only: bool
    partial_results: bool
    warnings: list[str] = Field(default_factory=list)
    candidates: list[PreparedSource] = Field(default_factory=list)


class PreparePaperSetRequest(FindPapersRequest):
    include_full_text: bool = True


class PreparePaperSetResponse(BaseModel):
    query: str
    profile: str
    direct_only: bool
    requested_count: int
    selected_count: int
    partial_results: bool
    warnings: list[str] = Field(default_factory=list)
    sources: list[PreparedSource] = Field(default_factory=list)


class CollectSourcesForTopicRequest(BaseModel):
    topic: str
    config_path: str | None = None
    db_path: str | None = None
    max_results: int = 5
    corpus: str = "papers"
    profile: str = "scientific"
    direct_only: bool = True
    force_refresh: bool = False
    include_full_text: bool = True


class CollectSourcesForTopicResponse(BaseModel):
    topic: str
    corpus: str
    profile: str
    direct_only: bool
    requested_count: int
    selected_count: int
    partial_results: bool
    warnings: list[str] = Field(default_factory=list)
    sources: list[PreparedSource] = Field(default_factory=list)


@dataclass(frozen=True)
class _CandidateAssessment:
    result: SearchResult
    source_type: str
    direct_paper_url: str | None
    selection_reason: str
    confidence: float
    paper_score: float


SUPPORTED_PREPARATION_PROFILES = {"scientific"}
SUPPORTED_CORPORA = {"papers"}
ACADEMIC_DOMAINS = {
    "aclanthology.org",
    "arxiv.org",
    "biorxiv.org",
    "dl.acm.org",
    "doi.org",
    "ieeexplore.ieee.org",
    "jmlr.org",
    "medrxiv.org",
    "nature.com",
    "openreview.net",
    "papers.nips.cc",
    "pmc.ncbi.nlm.nih.gov",
    "proceedings.mlr.press",
    "pubmed.ncbi.nlm.nih.gov",
    "science.org",
}
AGGREGATOR_DOMAINS = {
    "scholar.google.com",
    "semanticscholar.org",
    "www.semanticscholar.org",
    "researchgate.net",
    "www.researchgate.net",
}
DIRECT_PAPER_PATTERNS = (
    "aclanthology.org/",
    "arxiv.org/abs/",
    "arxiv.org/pdf/",
    "biorxiv.org/content/",
    "dl.acm.org/doi/",
    "doi.org/10.",
    "ieeexplore.ieee.org/document/",
    "jmlr.org/papers/",
    "medrxiv.org/content/",
    "nature.com/articles/",
    "openreview.net/forum",
    "papers.nips.cc/",
    "pmc.ncbi.nlm.nih.gov/articles/",
    "proceedings.mlr.press/",
    "pubmed.ncbi.nlm.nih.gov/",
    "science.org/doi/",
)
PAPER_HINTS = (
    "abstract",
    "conference",
    "journal",
    "paper",
    "preprint",
    "proceedings",
    "research",
    "study",
)
MAX_PREPARATION_SEARCH_MULTIPLIER = 4


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


def find_papers(request: FindPapersRequest, *, transport: httpx.BaseTransport | None = None) -> FindPapersResponse:
    settings, _ = resolve_runtime(request.config_path, request.db_path)
    requested_count = _validate_requested_count(request.count, settings.search.max_limit)
    search_response, candidates = _find_paper_candidates(
        query=request.query,
        config_path=request.config_path,
        db_path=request.db_path,
        requested_count=requested_count,
        profile=request.profile,
        direct_only=request.direct_only,
        force_refresh=request.force_refresh,
        transport=transport,
    )
    partial_results = search_response.partial_results or len(candidates) < requested_count
    warnings = list(search_response.warnings)
    if len(candidates) < requested_count:
        warnings.append(
            f"prepared only {len(candidates)} paper-like candidates out of {requested_count} requested."
        )
    return FindPapersResponse(
        query=search_response.query,
        profile=request.profile,
        direct_only=request.direct_only,
        partial_results=partial_results,
        warnings=warnings,
        candidates=[
            PreparedSource(
                title=candidate.result.title,
                url=candidate.result.canonical_url,
                published=candidate.result.published_at,
                summary=candidate.result.snippet or None,
                selection_reason=candidate.selection_reason,
                confidence=candidate.confidence,
                source_type=candidate.source_type,
                direct_paper_url=candidate.direct_paper_url,
                search_score=candidate.result.score,
                search_snippet=candidate.result.snippet,
                from_search_cache=search_response.from_cache,
            )
            for candidate in candidates
        ],
    )


def prepare_paper_set(request: PreparePaperSetRequest, *, transport: httpx.BaseTransport | None = None) -> PreparePaperSetResponse:
    settings, _ = resolve_runtime(request.config_path, request.db_path)
    requested_count = _validate_requested_count(request.count, settings.search.max_limit)
    candidate_pool_count = min(
        settings.search.max_limit,
        max(requested_count, requested_count * MAX_PREPARATION_SEARCH_MULTIPLIER),
    )
    search_response, candidates = _find_paper_candidates(
        query=request.query,
        config_path=request.config_path,
        db_path=request.db_path,
        requested_count=candidate_pool_count,
        profile=request.profile,
        direct_only=request.direct_only,
        force_refresh=request.force_refresh,
        transport=transport,
    )
    warnings = list(search_response.warnings)
    if len(candidates) < requested_count:
        warnings.append(
            f"prepared only {len(candidates)} paper-like candidates out of {requested_count} requested."
        )
    selected: list[PreparedSource] = []
    for candidate in candidates:
        if len(selected) >= requested_count:
            break
        candidate_url = candidate.result.canonical_url
        if candidate.source_type == "paper_pdf":
            warnings.append(f"skipped PDF-only candidate without HTML extraction support: {candidate_url}")
            continue
        try:
            extracted = extract_document_record(
                ExtractRequest(
                    url=candidate_url,
                    config_path=request.config_path,
                    db_path=request.db_path,
                    force_refresh=request.force_refresh,
                ),
                transport=transport,
            )
        except SonarError as exc:
            warnings.append(f"failed to prepare candidate {candidate_url}: {exc.message}")
            continue
        selected.append(
            PreparedSource(
                title=extracted.title or candidate.result.title,
                url=extracted.canonical_url,
                published=extracted.published_at or candidate.result.published_at,
                authors=_split_authors(extracted.byline),
                summary=_best_effort_summary(extracted.excerpt, extracted.text),
                full_text=extracted.text if request.include_full_text else None,
                selection_reason=candidate.selection_reason,
                confidence=candidate.confidence,
                source_type=candidate.source_type,
                direct_paper_url=candidate.direct_paper_url or extracted.canonical_url,
                document_id=extracted.document_id,
                search_score=candidate.result.score,
                search_snippet=candidate.result.snippet,
                from_search_cache=search_response.from_cache,
                from_extract_cache=extracted.from_cache,
            )
        )
    partial_results = search_response.partial_results or len(selected) < requested_count
    if len(selected) < requested_count:
        warnings.append(f"prepared {len(selected)} sources out of {requested_count} requested.")
    return PreparePaperSetResponse(
        query=search_response.query,
        profile=request.profile,
        direct_only=request.direct_only,
        requested_count=requested_count,
        selected_count=len(selected),
        partial_results=partial_results,
        warnings=warnings,
        sources=selected,
    )


def collect_sources_for_topic(
    request: CollectSourcesForTopicRequest,
    *,
    transport: httpx.BaseTransport | None = None,
) -> CollectSourcesForTopicResponse:
    if request.corpus not in SUPPORTED_CORPORA:
        supported = ", ".join(sorted(SUPPORTED_CORPORA))
        raise SonarBadRequestError(f"Corpus must be one of: {supported}.")
    prepared = prepare_paper_set(
        PreparePaperSetRequest(
            query=request.topic,
            config_path=request.config_path,
            db_path=request.db_path,
            count=request.max_results,
            profile=request.profile,
            direct_only=request.direct_only,
            force_refresh=request.force_refresh,
            include_full_text=request.include_full_text,
        ),
        transport=transport,
    )
    return CollectSourcesForTopicResponse(
        topic=request.topic,
        corpus=request.corpus,
        profile=request.profile,
        direct_only=request.direct_only,
        requested_count=request.max_results,
        selected_count=prepared.selected_count,
        partial_results=prepared.partial_results,
        warnings=prepared.warnings,
        sources=prepared.sources,
    )


def _resolve_document(repo: Repository, request: ExtractRequest):
    if request.document_id:
        return repo.get_document_by_id(request.document_id)
    if request.url:
        return repo.get_document_by_canonical_url(canonicalize_url(request.url))
    return None


def _select_paper_candidates(
    results: list[SearchResult],
    *,
    count: int,
    direct_only: bool,
) -> list[_CandidateAssessment]:
    assessed = []
    for result in results:
        candidate = _assess_paper_candidate(result, direct_only=direct_only)
        if candidate is not None:
            assessed.append(candidate)
    assessed.sort(key=lambda item: (item.paper_score, item.result.score), reverse=True)
    return assessed[:count]


def _find_paper_candidates(
    *,
    query: str,
    config_path: str | None,
    db_path: str | None,
    requested_count: int,
    profile: str,
    direct_only: bool,
    force_refresh: bool,
    transport: httpx.BaseTransport | None,
) -> tuple[SearchResponse, list[_CandidateAssessment]]:
    settings, _ = resolve_runtime(config_path, db_path)
    _validate_preparation_profile(profile)
    search_response = search_web(
        SearchRequest(
            query=query,
            config_path=config_path,
            db_path=db_path,
            limit=min(
                settings.search.max_limit,
                max(requested_count, requested_count * MAX_PREPARATION_SEARCH_MULTIPLIER),
            ),
            force_refresh=force_refresh,
        ),
        transport=transport,
    )
    candidates = _select_paper_candidates(
        search_response.results,
        count=requested_count,
        direct_only=direct_only,
    )
    return search_response, candidates


def _assess_paper_candidate(result: SearchResult, *, direct_only: bool) -> _CandidateAssessment | None:
    lower_url = result.canonical_url.lower()
    lower_title = result.title.lower()
    lower_snippet = result.snippet.lower()
    domain = result.domain.lower()
    reasons: list[str] = []
    paper_score = float(result.score) * 0.2
    source_type = "web_result"
    direct_paper_url: str | None = None

    is_pdf = lower_url.endswith(".pdf")
    is_direct = is_pdf or any(pattern in lower_url for pattern in DIRECT_PAPER_PATTERNS)
    is_academic = _domain_matches(domain, ACADEMIC_DOMAINS)
    is_aggregator = _domain_matches(domain, AGGREGATOR_DOMAINS)
    has_paper_hints = any(hint in lower_title or hint in lower_snippet for hint in PAPER_HINTS)

    if is_direct:
        source_type = "paper_pdf" if is_pdf else "paper_landing_page"
        direct_paper_url = result.canonical_url
        paper_score += 0.55 if not is_pdf else 0.35
        reasons.append("direct paper page" if not is_pdf else "direct paper PDF")
    if is_academic:
        paper_score += 0.3
        reasons.append("academic source domain")
    if has_paper_hints:
        paper_score += 0.15
        reasons.append("paper-like search metadata")
    if is_aggregator:
        source_type = "catalog"
        paper_score -= 0.25
        reasons.append("aggregator listing")

    if direct_only and not is_direct:
        return None
    if not direct_only and source_type == "web_result" and not (is_academic or has_paper_hints):
        return None

    confidence = round(max(0.05, min(0.99, paper_score / 1.4)), 3)
    selection_reason = "; ".join(dict.fromkeys(reasons)) or "ranked search relevance"
    return _CandidateAssessment(
        result=result,
        source_type=source_type,
        direct_paper_url=direct_paper_url,
        selection_reason=selection_reason,
        confidence=confidence,
        paper_score=paper_score,
    )


def _validate_preparation_profile(profile: str) -> None:
    if profile not in SUPPORTED_PREPARATION_PROFILES:
        supported = ", ".join(sorted(SUPPORTED_PREPARATION_PROFILES))
        raise SonarBadRequestError(f"Profile must be one of: {supported}.")


def _validate_requested_count(count: int, max_limit: int) -> int:
    if count < 1 or count > max_limit:
        raise SonarBadRequestError(f"Requested count must be between 1 and {max_limit}.")
    return count


def _split_authors(byline: str | None) -> list[str]:
    if not byline:
        return []
    return [part.strip() for part in re.split(r"\s*(?:,|;| and )\s*", byline) if part.strip()]


def _best_effort_summary(excerpt: str | None, text: str) -> str | None:
    if excerpt:
        return excerpt
    normalized = " ".join(text.split())
    if not normalized:
        return None
    return normalized[:400]


def _domain_matches(domain: str, candidates: set[str]) -> bool:
    return any(domain == candidate or domain.endswith(f".{candidate}") for candidate in candidates)
