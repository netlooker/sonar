"""SQLite storage for Sonar artifacts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass
class SearchRunRow:
    run_id: str
    query: str
    variants: list[str]
    partial_results: bool
    warnings: list[str]
    created_at: float
    expires_at: float


class Repository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def initialize(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS search_runs (
                run_id TEXT PRIMARY KEY,
                signature TEXT NOT NULL UNIQUE,
                query TEXT NOT NULL,
                variants_json TEXT NOT NULL,
                partial_results INTEGER NOT NULL,
                warnings_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS search_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                canonical_url TEXT NOT NULL,
                snippet TEXT NOT NULL,
                engine TEXT NOT NULL,
                position INTEGER NOT NULL,
                domain TEXT NOT NULL,
                published_at TEXT,
                score REAL NOT NULL,
                FOREIGN KEY(run_id) REFERENCES search_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                canonical_url TEXT NOT NULL UNIQUE,
                final_url TEXT NOT NULL,
                status TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                content_type TEXT NOT NULL,
                fetched_at REAL NOT NULL,
                fetch_expires_at REAL NOT NULL,
                extractable INTEGER NOT NULL,
                title TEXT,
                byline TEXT,
                published_at TEXT,
                language TEXT,
                excerpt TEXT,
                text TEXT,
                word_count INTEGER,
                extract_hash TEXT,
                extract_expires_at REAL
            );

            CREATE TABLE IF NOT EXISTS domain_priors (
                domain TEXT PRIMARY KEY,
                weight REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS prepared_bundles (
                bundle_id TEXT PRIMARY KEY,
                bundle_version INTEGER NOT NULL,
                artifact_type TEXT NOT NULL,
                created_at REAL NOT NULL,
                request_fingerprint TEXT NOT NULL,
                query TEXT NOT NULL,
                corpus TEXT,
                profile TEXT NOT NULL,
                direct_only INTEGER NOT NULL,
                requested_count INTEGER NOT NULL,
                selected_count INTEGER NOT NULL,
                partial_results INTEGER NOT NULL,
                bundle_path TEXT,
                search_run_id TEXT,
                warnings_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS prepared_bundle_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bundle_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                document_id TEXT,
                origin_url TEXT NOT NULL,
                url TEXT NOT NULL,
                direct_paper_url TEXT,
                title TEXT NOT NULL,
                authors_json TEXT NOT NULL,
                author_raw TEXT,
                published TEXT,
                source_type TEXT NOT NULL,
                retrieved_at REAL NOT NULL,
                selection_reason TEXT NOT NULL,
                confidence REAL NOT NULL,
                summary TEXT,
                abstract TEXT,
                full_text_path TEXT,
                extraction_status TEXT NOT NULL,
                extraction_method TEXT NOT NULL,
                content_type TEXT,
                search_score REAL NOT NULL,
                search_snippet TEXT NOT NULL,
                from_search_cache INTEGER NOT NULL,
                from_extract_cache INTEGER NOT NULL,
                source_warnings_json TEXT NOT NULL,
                FOREIGN KEY(bundle_id) REFERENCES prepared_bundles(bundle_id)
            );
            """
        )
        self._ensure_column("documents", "source_format", "TEXT")
        self._ensure_column("documents", "extraction_method", "TEXT")
        self._ensure_column("documents", "extraction_status", "TEXT")
        self._ensure_column("documents", "abstract", "TEXT")
        self.conn.commit()

    def upsert_domain_priors(self, priors: dict[str, float]) -> None:
        self.conn.execute("DELETE FROM domain_priors")
        self.conn.executemany(
            "INSERT INTO domain_priors(domain, weight) VALUES(?, ?)",
            [(domain, weight) for domain, weight in priors.items()],
        )
        self.conn.commit()

    def get_domain_priors(self) -> dict[str, float]:
        rows = self.conn.execute("SELECT domain, weight FROM domain_priors").fetchall()
        return {str(row["domain"]): float(row["weight"]) for row in rows}

    def get_cached_search(self, signature: str, now: float) -> tuple[SearchRunRow, list[dict[str, object]]] | None:
        row = self.conn.execute(
            "SELECT * FROM search_runs WHERE signature = ? AND expires_at > ?",
            (signature, now),
        ).fetchone()
        if row is None:
            return None
        results = self.conn.execute(
            "SELECT title, url, canonical_url, snippet, engine, position, domain, published_at, score "
            "FROM search_results WHERE run_id = ? ORDER BY score DESC, id ASC",
            (row["run_id"],),
        ).fetchall()
        return (
            SearchRunRow(
                run_id=str(row["run_id"]),
                query=str(row["query"]),
                variants=json.loads(row["variants_json"]),
                partial_results=bool(row["partial_results"]),
                warnings=json.loads(row["warnings_json"]),
                created_at=float(row["created_at"]),
                expires_at=float(row["expires_at"]),
            ),
            [dict(item) for item in results],
        )

    def store_search_run(
        self,
        *,
        signature: str,
        run_id: str,
        query: str,
        variants: list[str],
        partial_results: bool,
        warnings: list[str],
        created_at: float,
        expires_at: float,
        results: list[dict[str, object]],
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO search_runs(run_id, signature, query, variants_json, partial_results, warnings_json, created_at, expires_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                signature,
                query,
                json.dumps(variants),
                int(partial_results),
                json.dumps(warnings),
                created_at,
                expires_at,
            ),
        )
        self.conn.execute("DELETE FROM search_results WHERE run_id = ?", (run_id,))
        self.conn.executemany(
            "INSERT INTO search_results(run_id, title, url, canonical_url, snippet, engine, position, domain, published_at, score) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id,
                    str(item["title"]),
                    str(item["url"]),
                    str(item["canonical_url"]),
                    str(item["snippet"]),
                    str(item["engine"]),
                    int(item["position"]),
                    str(item["domain"]),
                    item.get("published_at"),
                    float(item["score"]),
                )
                for item in results
            ],
        )
        self.conn.commit()

    def get_document_by_canonical_url(self, canonical_url: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM documents WHERE canonical_url = ?",
            (canonical_url,),
        ).fetchone()

    def get_document_by_id(self, document_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()

    def store_document_fetch(
        self,
        *,
        document_id: str,
        url: str,
        canonical_url: str,
        final_url: str,
        status: str,
        status_code: int,
        content_type: str,
        fetched_at: float,
        fetch_expires_at: float,
        extractable: bool,
        source_format: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO documents(
                document_id, url, canonical_url, final_url, status, status_code, content_type,
                fetched_at, fetch_expires_at, extractable, source_format
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_url) DO UPDATE SET
                document_id=excluded.document_id,
                url=excluded.url,
                final_url=excluded.final_url,
                status=excluded.status,
                status_code=excluded.status_code,
                content_type=excluded.content_type,
                fetched_at=excluded.fetched_at,
                fetch_expires_at=excluded.fetch_expires_at,
                extractable=excluded.extractable,
                source_format=excluded.source_format
            """,
            (
                document_id,
                url,
                canonical_url,
                final_url,
                status,
                status_code,
                content_type,
                fetched_at,
                fetch_expires_at,
                int(extractable),
                source_format,
            ),
        )
        self.conn.commit()

    def store_extract(
        self,
        *,
        document_id: str,
        title: str | None,
        byline: str | None,
        published_at: str | None,
        language: str | None,
        excerpt: str | None,
        abstract: str | None,
        text: str,
        word_count: int,
        extract_hash: str,
        extract_expires_at: float,
        extraction_method: str,
        extraction_status: str,
    ) -> None:
        self.conn.execute(
            """
            UPDATE documents
            SET title = ?, byline = ?, published_at = ?, language = ?, excerpt = ?, abstract = ?, text = ?,
                word_count = ?, extract_hash = ?, extract_expires_at = ?, extraction_method = ?,
                extraction_status = ?
            WHERE document_id = ?
            """,
            (
                title,
                byline,
                published_at,
                language,
                excerpt,
                abstract,
                text,
                word_count,
                extract_hash,
                extract_expires_at,
                extraction_method,
                extraction_status,
                document_id,
            ),
        )
        self.conn.commit()

    def store_prepared_bundle(self, bundle: Mapping[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO prepared_bundles(
                bundle_id, bundle_version, artifact_type, created_at, request_fingerprint, query, corpus,
                profile, direct_only, requested_count, selected_count, partial_results, bundle_path,
                search_run_id, warnings_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(bundle["bundle_id"]),
                int(bundle["bundle_version"]),
                str(bundle["artifact_type"]),
                float(bundle["created_at"]),
                str(bundle["request_fingerprint"]),
                str(bundle["query"]),
                bundle.get("corpus"),
                str(bundle["profile"]),
                int(bool(bundle["direct_only"])),
                int(bundle["requested_count"]),
                int(bundle["selected_count"]),
                int(bool(bundle["partial_results"])),
                bundle.get("bundle_path"),
                bundle.get("search_run_id"),
                json.dumps(bundle.get("warnings", [])),
            ),
        )
        self.conn.execute(
            "DELETE FROM prepared_bundle_sources WHERE bundle_id = ?",
            (str(bundle["bundle_id"]),),
        )
        self.conn.executemany(
            """
            INSERT INTO prepared_bundle_sources(
                bundle_id, source_id, document_id, origin_url, url, direct_paper_url, title, authors_json,
                author_raw, published, source_type, retrieved_at, selection_reason, confidence, summary,
                abstract, full_text_path, extraction_status, extraction_method, content_type, search_score,
                search_snippet, from_search_cache, from_extract_cache, source_warnings_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(bundle["bundle_id"]),
                    str(source["source_id"]),
                    source.get("document_id"),
                    str(source["origin_url"]),
                    str(source["url"]),
                    source.get("direct_paper_url"),
                    str(source["title"]),
                    json.dumps(source.get("authors", [])),
                    source.get("author_raw"),
                    source.get("published"),
                    str(source["source_type"]),
                    float(source["retrieved_at"]),
                    str(source["selection_reason"]),
                    float(source["confidence"]),
                    source.get("summary"),
                    source.get("abstract"),
                    source.get("full_text_path"),
                    str(source["extraction_status"]),
                    str(source["extraction_method"]),
                    source.get("content_type"),
                    float(source["search_score"]),
                    str(source["search_snippet"]),
                    int(bool(source["from_search_cache"])),
                    int(bool(source["from_extract_cache"])),
                    json.dumps(source.get("source_warnings", [])),
                )
                for source in bundle.get("sources", [])
            ],
        )
        self.conn.commit()

    def get_prepared_bundle(self, bundle_id: str) -> dict[str, Any] | None:
        bundle_row = self.conn.execute(
            "SELECT * FROM prepared_bundles WHERE bundle_id = ?",
            (bundle_id,),
        ).fetchone()
        if bundle_row is None:
            return None
        source_rows = self.conn.execute(
            "SELECT * FROM prepared_bundle_sources WHERE bundle_id = ? ORDER BY id ASC",
            (bundle_id,),
        ).fetchall()
        return {
            "artifact_type": str(bundle_row["artifact_type"]),
            "bundle_version": int(bundle_row["bundle_version"]),
            "bundle_id": str(bundle_row["bundle_id"]),
            "bundle_path": bundle_row["bundle_path"],
            "created_at": float(bundle_row["created_at"]),
            "request_fingerprint": str(bundle_row["request_fingerprint"]),
            "query": str(bundle_row["query"]),
            "corpus": bundle_row["corpus"],
            "profile": str(bundle_row["profile"]),
            "direct_only": bool(bundle_row["direct_only"]),
            "requested_count": int(bundle_row["requested_count"]),
            "selected_count": int(bundle_row["selected_count"]),
            "partial_results": bool(bundle_row["partial_results"]),
            "warnings": json.loads(bundle_row["warnings_json"]),
            "search_run_id": bundle_row["search_run_id"],
            "sources": [
                {
                    "source_id": str(source["source_id"]),
                    "document_id": source["document_id"],
                    "origin_url": str(source["origin_url"]),
                    "url": str(source["url"]),
                    "direct_paper_url": source["direct_paper_url"],
                    "title": str(source["title"]),
                    "authors": json.loads(source["authors_json"]),
                    "author_raw": source["author_raw"],
                    "published": source["published"],
                    "source_type": str(source["source_type"]),
                    "retrieved_at": float(source["retrieved_at"]),
                    "selection_reason": str(source["selection_reason"]),
                    "confidence": float(source["confidence"]),
                    "summary": source["summary"],
                    "abstract": source["abstract"],
                    "full_text_path": source["full_text_path"],
                    "extraction_status": str(source["extraction_status"]),
                    "extraction_method": str(source["extraction_method"]),
                    "content_type": source["content_type"],
                    "search_score": float(source["search_score"]),
                    "search_snippet": str(source["search_snippet"]),
                    "from_search_cache": bool(source["from_search_cache"]),
                    "from_extract_cache": bool(source["from_extract_cache"]),
                    "source_warnings": json.loads(source["source_warnings_json"]),
                }
                for source in source_rows
            ],
        }

    def _ensure_column(self, table: str, column: str, column_type: str) -> None:
        rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        names = {str(row["name"]) for row in rows}
        if column not in names:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
