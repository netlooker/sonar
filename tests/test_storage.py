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


def test_repository_stores_document_body_and_retrieval_provenance(tmp_path):
    repo = Repository(tmp_path / "sonar.sqlite")
    repo.initialize()
    repo.store_document_fetch(
        document_id="doc-1",
        url="https://example.com",
        canonical_url="https://example.com/",
        final_url="https://example.com/",
        status="fetched",
        status_code=200,
        content_type="text/html",
        fetched_at=1.0,
        fetch_expires_at=100.0,
        extractable=True,
        source_format="html",
        body=b"<html>body</html>",
        body_hash="hash",
        body_expires_at=100.0,
        retrieval_backend="cloakbrowser",
        rendered=True,
        retrieval_attempts=["http", "scrapling_http", "cloakbrowser"],
        retrieval_warnings=["thin_text_triggered_cloakbrowser_fallback"],
        fallback_reason="thin_text",
    )

    row = repo.get_document_by_id("doc-1")
    repo.close()

    assert row is not None
    assert bytes(row["body"]) == b"<html>body</html>"
    assert row["retrieval_backend"] == "cloakbrowser"
    assert bool(row["rendered"]) is True
    assert row["fallback_reason"] == "thin_text"


def test_repository_migrates_legacy_documents_table_additively(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE documents (
            document_id TEXT PRIMARY KEY, url TEXT NOT NULL, canonical_url TEXT NOT NULL UNIQUE,
            final_url TEXT NOT NULL, status TEXT NOT NULL, status_code INTEGER NOT NULL,
            content_type TEXT NOT NULL, fetched_at REAL NOT NULL, fetch_expires_at REAL NOT NULL,
            extractable INTEGER NOT NULL, title TEXT, byline TEXT, published_at TEXT, language TEXT,
            excerpt TEXT, text TEXT, word_count INTEGER, extract_hash TEXT, extract_expires_at REAL
        )
        """
    )
    conn.execute(
        "INSERT INTO documents(document_id, url, canonical_url, final_url, status, status_code, content_type, fetched_at, fetch_expires_at, extractable) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "legacy",
            "https://example.com",
            "https://example.com/",
            "https://example.com/",
            "fetched",
            200,
            "text/html",
            1.0,
            2.0,
            1,
        ),
    )
    conn.commit()
    conn.close()

    repo = Repository(path)
    repo.initialize()
    row = repo.get_document_by_id("legacy")
    columns = {
        item["name"]
        for item in repo.conn.execute("PRAGMA table_info(documents)").fetchall()
    }
    repo.close()

    assert row is not None
    assert row["retrieval_backend"] is None
    assert bool(row["rendered"]) is False
    assert {
        "body",
        "retrieval_backend",
        "retrieval_attempts_json",
        "fallback_reason",
    }.issubset(columns)
