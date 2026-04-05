from sonar.storage import Repository


def test_repository_stores_and_reads_search_cache(tmp_path):
    repo = Repository(tmp_path / "sonar.sqlite")
    repo.initialize()
    repo.store_search_run(
        signature="sig",
        run_id="run-1",
        query="query",
        variants=["query"],
        partial_results=False,
        warnings=[],
        created_at=1.0,
        expires_at=100.0,
        results=[
            {
                "title": "Example",
                "url": "https://example.com",
                "canonical_url": "https://example.com/",
                "snippet": "snippet",
                "engine": "duckduckgo",
                "position": 1,
                "domain": "example.com",
                "published_at": None,
                "score": 0.8,
            }
        ],
    )

    cached = repo.get_cached_search("sig", now=2.0)
    repo.close()

    assert cached is not None
    run, results = cached
    assert run.run_id == "run-1"
    assert results[0]["title"] == "Example"
