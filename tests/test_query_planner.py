from sonar.query_planner import generate_query_variants, normalize_query
from sonar.ranking import canonicalize_url, dedupe_results


def test_normalize_query_collapses_whitespace():
    assert normalize_query("  latest   ai \n search   ") == "latest ai search"


def test_generate_query_variants_keeps_original_and_focused_variant():
    variants = generate_query_variants("what is the latest open source ai search engine")

    assert variants[0] == "what is the latest open source ai search engine"
    assert "latest open source search engine" in variants
    assert len(variants) <= 3


def test_generate_query_variants_preserves_quotes():
    variants = generate_query_variants('news about "open source search" ranking')

    assert '"open source search"' in variants


def test_canonicalize_url_strips_tracking_params_and_fragment():
    assert (
        canonicalize_url("https://Example.com/path?a=1&utm_source=x&fbclid=y#frag")
        == "https://example.com/path?a=1"
    )


def test_dedupe_results_keeps_best_scored_canonical_url():
    results = [
        {"canonical_url": "https://example.com/a", "score": 0.4},
        {"canonical_url": "https://example.com/a", "score": 0.9},
    ]

    deduped = dedupe_results(results)

    assert deduped == [{"canonical_url": "https://example.com/a", "score": 0.9}]
