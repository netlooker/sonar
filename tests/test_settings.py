from pathlib import Path

import pytest

from sonar.errors import SonarNotFoundError
from sonar.settings import load_settings


def test_load_settings_reads_example_defaults():
    settings = load_settings("config/sonar.example.toml")

    assert settings.searxng.base_url == "http://127.0.0.1:8080"
    assert settings.database.path == "~/.sonar/sonar.sqlite"
    assert settings.http.host == "127.0.0.1"
    assert settings.http.port == 8001
    assert settings.cache.search_ttl_seconds == 900
    assert settings.cache.extract_ttl_seconds == 86400
    assert settings.fetch.max_body_bytes == 2097152
    assert settings.domain_priors["docs.python.org"] == 0.35


def test_load_settings_uses_defaults_without_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    settings = load_settings()

    assert settings.database.path == "~/.sonar/sonar.sqlite"
    assert settings.searxng.base_url == "http://127.0.0.1:8080"


def test_load_settings_raises_for_missing_explicit_config():
    with pytest.raises(SonarNotFoundError, match="Sonar config not found"):
        load_settings("/tmp/does-not-exist-sonar.toml")


def test_load_settings_applies_secret_overlay(tmp_path, monkeypatch):
    config = tmp_path / "sonar.toml"
    secrets = tmp_path / "secret.toml"
    secrets.write_text("[searxng]\nauthorization_header = 'Bearer local'\n", encoding="utf-8")
    config.write_text(
        f"[secrets]\noverlay_path = '{secrets}'\n\n[searxng]\nbase_url = 'http://localhost:9999'\n",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.searxng.base_url == "http://localhost:9999"
    assert settings.searxng.authorization_header == "Bearer local"


def test_load_settings_applies_env_overrides(monkeypatch):
    monkeypatch.setenv("SONAR_SEARXNG_BASE_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("SONAR_DB", "/tmp/sonar.sqlite")

    settings = load_settings("config/sonar.example.toml")

    assert settings.searxng.base_url == "http://127.0.0.1:9999"
    assert settings.database.path == "/tmp/sonar.sqlite"


def test_load_settings_prefers_project_config_location(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sonar.toml").write_text("[http]\nport = 9001\n", encoding="utf-8")
    (tmp_path / "sonar.toml").write_text("[http]\nport = 9002\n", encoding="utf-8")

    settings = load_settings()

    assert settings.config_path == Path("config/sonar.toml")
    assert settings.http.port == 9001
