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


def test_repository_stores_prepared_bundle_registry(tmp_path):
    repo = Repository(tmp_path / "sonar.sqlite")
    repo.initialize()
    repo.store_prepared_bundle(
        {
            "artifact_type": "prepared_source_bundle",
            "bundle_version": 1,
            "bundle_id": "bundle-1",
            "bundle_path": str(tmp_path / "bundle-1"),
            "created_at": 10.0,
            "request_fingerprint": "fingerprint",
            "query": "agent memory",
            "corpus": "papers",
            "profile": "scientific",
            "direct_only": True,
            "requested_count": 1,
            "selected_count": 1,
            "partial_results": False,
            "warnings": [],
            "search_run_id": "run-1",
            "sources": [
                {
                    "source_id": "source-1",
                    "document_id": "doc-1",
                    "origin_url": "https://arxiv.org/abs/1",
                    "url": "https://arxiv.org/abs/1",
                    "direct_paper_url": "https://arxiv.org/pdf/1.pdf",
                    "title": "Paper",
                    "authors": ["Alice Example"],
                    "author_raw": "Alice Example",
                    "published": "2024-01-01",
                    "source_type": "paper_landing_page",
                    "retrieved_at": 10.0,
                    "selection_reason": "direct paper page",
                    "confidence": 0.9,
                    "summary": "summary",
                    "abstract": "abstract",
                    "full_text": "full text",
                    "full_text_path": str(tmp_path / "bundle-1" / "source_01.txt"),
                    "extraction_status": "full",
                    "extraction_method": "html+pdf",
                    "content_type": "application/pdf",
                    "search_score": 1.0,
                    "search_snippet": "paper",
                    "from_search_cache": False,
                    "from_extract_cache": True,
                    "source_warnings": [],
                }
            ],
        }
    )

    stored = repo.get_prepared_bundle("bundle-1")
    repo.close()

    assert stored is not None
    assert stored["bundle_id"] == "bundle-1"
    assert stored["sources"][0]["source_id"] == "source-1"
