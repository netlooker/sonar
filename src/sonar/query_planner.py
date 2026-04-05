"""Deterministic query normalization and expansion."""

from __future__ import annotations

import re


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "how",
    "in",
    "is",
    "of",
    "on",
    "the",
    "to",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
}


def normalize_query(query: str) -> str:
    return " ".join(query.strip().split())


def generate_query_variants(query: str) -> list[str]:
    normalized = normalize_query(query)
    if not normalized:
        return []

    variants = [normalized]
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", normalized)
    if len(tokens) >= 5:
        focused = [token for token in tokens if token.lower() not in STOPWORDS and len(token) >= 3][:8]
        if focused:
            variants.append(" ".join(focused))

    phrases = re.findall(r'"([^"]+)"', normalized)
    if phrases:
        phrase_variant = " ".join(f'"{normalize_query(phrase)}"' for phrase in phrases if normalize_query(phrase))
        if phrase_variant:
            variants.append(phrase_variant)

    unique: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        key = normalize_query(variant).lower()
        if key not in seen:
            unique.append(variant)
            seen.add(key)
        if len(unique) == 3:
            break
    return unique
