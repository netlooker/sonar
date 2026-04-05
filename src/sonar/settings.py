"""Application settings for Sonar."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import SonarNotFoundError


DEFAULT_CONFIG_PATHS = (
    Path("config/sonar.toml"),
    Path("sonar.toml"),
)
DEFAULT_DB_PATH = "~/.sonar/sonar.sqlite"
DEFAULT_SEARXNG_URL = "http://127.0.0.1:8080"


@dataclass(frozen=True)
class SearxNGSettings:
    base_url: str = DEFAULT_SEARXNG_URL
    api_key: str | None = None
    authorization_header: str | None = None


@dataclass(frozen=True)
class DatabaseSettings:
    path: str = DEFAULT_DB_PATH

    def db_path(self) -> Path:
        return Path(self.path).expanduser()


@dataclass(frozen=True)
class HttpSettings:
    host: str = "127.0.0.1"
    port: int = 8001
    auth_mode: str = "none"


@dataclass(frozen=True)
class CacheSettings:
    search_ttl_seconds: int = 900
    extract_ttl_seconds: int = 86400


@dataclass(frozen=True)
class FetchSettings:
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 20.0
    max_body_bytes: int = 2 * 1024 * 1024
    user_agent: str = "Sonar/0.1"


@dataclass(frozen=True)
class SearchSettings:
    default_limit: int = 8
    max_limit: int = 20


@dataclass(frozen=True)
class SecretsSettings:
    overlay_path: str | None = "secrets/sonar.secrets.toml"

    def resolved_overlay(self) -> Path | None:
        if not self.overlay_path:
            return None
        return Path(self.overlay_path).expanduser()


@dataclass(frozen=True)
class AppSettings:
    config_path: Path | None = None
    searxng: SearxNGSettings = field(default_factory=SearxNGSettings)
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    http: HttpSettings = field(default_factory=HttpSettings)
    cache: CacheSettings = field(default_factory=CacheSettings)
    fetch: FetchSettings = field(default_factory=FetchSettings)
    search: SearchSettings = field(default_factory=SearchSettings)
    secrets: SecretsSettings = field(default_factory=SecretsSettings)
    domain_priors: dict[str, float] = field(default_factory=dict)


def load_settings(config_path: str | Path | None = None) -> AppSettings:
    resolved_config_path, require_exists = _resolve_config_path(config_path)
    config = _load_toml(resolved_config_path, require_exists=require_exists)
    secrets = _load_secrets_overlay(config)
    merged = _deep_merge(secrets, config)

    settings = AppSettings(
        config_path=resolved_config_path if resolved_config_path.exists() else None,
        searxng=SearxNGSettings(
            base_url=os.environ.get(
                "SONAR_SEARXNG_BASE_URL",
                merged.get("searxng", {}).get("base_url", DEFAULT_SEARXNG_URL),
            ),
            api_key=os.environ.get(
                "SONAR_SEARXNG_API_KEY",
                merged.get("searxng", {}).get("api_key"),
            ),
            authorization_header=os.environ.get(
                "SONAR_SEARXNG_AUTHORIZATION_HEADER",
                merged.get("searxng", {}).get("authorization_header"),
            ),
        ),
        database=DatabaseSettings(
            path=os.environ.get(
                "SONAR_DB",
                merged.get("database", {}).get("path", DEFAULT_DB_PATH),
            )
        ),
        http=HttpSettings(
            host=os.environ.get("SONAR_HTTP_HOST", merged.get("http", {}).get("host", "127.0.0.1")),
            port=int(os.environ.get("SONAR_HTTP_PORT", merged.get("http", {}).get("port", 8001))),
            auth_mode=os.environ.get(
                "SONAR_HTTP_AUTH_MODE",
                merged.get("http", {}).get("auth_mode", "none"),
            ),
        ),
        cache=CacheSettings(
            search_ttl_seconds=int(
                os.environ.get(
                    "SONAR_SEARCH_TTL_SECONDS",
                    merged.get("cache", {}).get("search_ttl_seconds", 900),
                )
            ),
            extract_ttl_seconds=int(
                os.environ.get(
                    "SONAR_EXTRACT_TTL_SECONDS",
                    merged.get("cache", {}).get("extract_ttl_seconds", 86400),
                )
            ),
        ),
        fetch=FetchSettings(
            connect_timeout_seconds=float(
                os.environ.get(
                    "SONAR_CONNECT_TIMEOUT_SECONDS",
                    merged.get("fetch", {}).get("connect_timeout_seconds", 10.0),
                )
            ),
            read_timeout_seconds=float(
                os.environ.get(
                    "SONAR_READ_TIMEOUT_SECONDS",
                    merged.get("fetch", {}).get("read_timeout_seconds", 20.0),
                )
            ),
            max_body_bytes=int(
                os.environ.get(
                    "SONAR_MAX_BODY_BYTES",
                    merged.get("fetch", {}).get("max_body_bytes", 2 * 1024 * 1024),
                )
            ),
            user_agent=os.environ.get(
                "SONAR_USER_AGENT",
                merged.get("fetch", {}).get("user_agent", "Sonar/0.1"),
            ),
        ),
        search=SearchSettings(
            default_limit=int(
                os.environ.get(
                    "SONAR_DEFAULT_LIMIT",
                    merged.get("search", {}).get("default_limit", 8),
                )
            ),
            max_limit=int(
                os.environ.get(
                    "SONAR_MAX_LIMIT",
                    merged.get("search", {}).get("max_limit", 20),
                )
            ),
        ),
        secrets=SecretsSettings(
            overlay_path=os.environ.get(
                "SONAR_SECRETS_FILE",
                merged.get("secrets", {}).get("overlay_path", "secrets/sonar.secrets.toml"),
            )
        ),
        domain_priors={
            domain: float(weight)
            for domain, weight in merged.get("ranking", {}).get("domain_priors", {}).items()
        },
    )
    return settings


def _resolve_config_path(config_path: str | Path | None) -> tuple[Path, bool]:
    if config_path:
        return Path(config_path), True

    env_path = os.environ.get("SONAR_CONFIG")
    if env_path:
        return Path(env_path), True

    for candidate in DEFAULT_CONFIG_PATHS:
        if candidate.exists():
            return candidate, False
    return DEFAULT_CONFIG_PATHS[0], False


def _load_toml(config_path: Path, *, require_exists: bool = False) -> dict[str, Any]:
    if not config_path.exists():
        if require_exists:
            raise SonarNotFoundError(f"Sonar config not found: {config_path}")
        return {}
    with config_path.open("rb") as handle:
        return tomllib.load(handle)


def _load_secrets_overlay(config: dict[str, Any]) -> dict[str, Any]:
    overlay_env = os.environ.get("SONAR_SECRETS_FILE")
    overlay_path = overlay_env or config.get("secrets", {}).get("overlay_path")
    if not overlay_path:
        return {}
    path = Path(overlay_path).expanduser()
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
