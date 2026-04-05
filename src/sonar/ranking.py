"""URL normalization, dedupe, and ranking."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src"}


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    filtered = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_PARAMS:
            continue
        filtered.append((key, value))
    query = urlencode(sorted(filtered))
    return urlunsplit((scheme, netloc, path, query, ""))


def url_domain(url: str) -> str:
    return urlsplit(url).netloc.lower()


def query_signature(
    query: str,
    *,
    limit: int,
    engines: list[str] | None,
    categories: list[str] | None,
    language: str | None,
    freshness: str,
) -> str:
    payload = "|".join(
        [
            query.strip().lower(),
            str(limit),
            ",".join(sorted(engines or [])),
            ",".join(sorted(categories or [])),
            language or "",
            freshness,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def rank_results(results: list[dict[str, object]], query: str, domain_priors: dict[str, float]) -> list[dict[str, object]]:
    query_terms = {token.lower() for token in query.split() if token}
    ranked: list[dict[str, object]] = []
    for result in results:
        title = str(result.get("title", ""))
        snippet = str(result.get("snippet", ""))
        domain = str(result.get("domain", ""))
        overlap_terms = _tokenize(title) | _tokenize(snippet)
        overlap = len(query_terms & overlap_terms) / max(1, len(query_terms))
        freshness = _freshness_boost(result.get("published_at"))
        position = int(result.get("position", 99))
        position_score = max(0.0, 1.0 - (position - 1) * 0.1)
        domain_bonus = float(domain_priors.get(domain, 0.0))
        score = round(position_score + overlap * 0.8 + freshness + domain_bonus, 6)
        enriched = dict(result)
        enriched["score"] = score
        ranked.append(enriched)
    ranked.sort(key=lambda item: float(item["score"]), reverse=True)
    return ranked


def dedupe_results(results: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: dict[str, dict[str, object]] = {}
    for result in results:
        canonical_url = str(result["canonical_url"])
        current = deduped.get(canonical_url)
        if current is None or float(result.get("score", 0.0)) > float(current.get("score", 0.0)):
            deduped[canonical_url] = result
    return list(deduped.values())


def _tokenize(text: str) -> set[str]:
    return {
        token.strip(".,:;!?()[]{}\"'").lower()
        for token in text.split()
        if token.strip(".,:;!?()[]{}\"'")
    }


def _freshness_boost(published_at: object) -> float:
    if not published_at:
        return 0.0
    try:
        published = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if published.tzinfo is None:
        published = published.replace(tzinfo=UTC)
    age_days = max(0.0, (datetime.now(UTC) - published).total_seconds() / 86400.0)
    return round(max(0.0, 0.4 * math.exp(-age_days / 30.0)), 6)
