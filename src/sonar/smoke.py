"""Basic runtime smoke checks for Sonar."""

from __future__ import annotations

import argparse
import json

from .service_api import HealthRequest, SearchRequest, runtime_requirements, search_web


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Sonar smoke check.")
    parser.add_argument("--config", dest="config_path", default=None)
    parser.add_argument("--db", dest="db_path", default=None)
    parser.add_argument("--query", default=None)
    args = parser.parse_args()

    health = runtime_requirements(HealthRequest(config_path=args.config_path, db_path=args.db_path))
    payload = {"health": health.model_dump()}
    if args.query:
        search = search_web(SearchRequest(query=args.query, config_path=args.config_path, db_path=args.db_path))
        payload["search"] = search.model_dump()
    print(json.dumps(payload, indent=2))
