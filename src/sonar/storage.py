"""SQLite storage for Sonar artifacts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


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
            """
        )
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
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO documents(
                document_id, url, canonical_url, final_url, status, status_code, content_type,
                fetched_at, fetch_expires_at, extractable
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_url) DO UPDATE SET
                document_id=excluded.document_id,
                url=excluded.url,
                final_url=excluded.final_url,
                status=excluded.status,
                status_code=excluded.status_code,
                content_type=excluded.content_type,
                fetched_at=excluded.fetched_at,
                fetch_expires_at=excluded.fetch_expires_at,
                extractable=excluded.extractable
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
        text: str,
        word_count: int,
        extract_hash: str,
        extract_expires_at: float,
    ) -> None:
        self.conn.execute(
            """
            UPDATE documents
            SET title = ?, byline = ?, published_at = ?, language = ?, excerpt = ?, text = ?,
                word_count = ?, extract_hash = ?, extract_expires_at = ?
            WHERE document_id = ?
            """,
            (
                title,
                byline,
                published_at,
                language,
                excerpt,
                text,
                word_count,
                extract_hash,
                extract_expires_at,
                document_id,
            ),
        )
        self.conn.commit()
