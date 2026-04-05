import json
import sys
from pathlib import Path

import pytest

mcp = pytest.importorskip("mcp")

from sonar.mcp_server import _require_server_config, build_server, runtime_requirements


def test_runtime_requirements_reports_database_path(tmp_path):
    response = runtime_requirements(config_path="config/sonar.example.toml", db_path=str(tmp_path / "sonar.sqlite"))

    assert response["database_path"] == str(tmp_path / "sonar.sqlite")


def test_build_server_lists_expected_tools():
    server = build_server()
    tool_names = set(server._tool_manager._tools.keys())

    assert "sonar_health" in tool_names
    assert "sonar_search" in tool_names
    assert "sonar_fetch" in tool_names
    assert "sonar_extract" in tool_names


def test_example_mcp_config_is_valid_json():
    payload = json.loads(Path("config/sonar.mcp.example.json").read_text(encoding="utf-8"))

    assert "mcpServers" in payload
    assert payload["mcpServers"]["sonar"]["env"]["SONAR_MCP_TRANSPORT"] == "stdio"


def test_mcp_entrypoint_requires_config(monkeypatch):
    monkeypatch.delenv("SONAR_CONFIG", raising=False)

    with pytest.raises(RuntimeError, match="SONAR_CONFIG is required"):
        _require_server_config()


def test_health_tool_uses_shared_runtime(tmp_path):
    server = build_server()
    result = server._tool_manager._tools["sonar_health"].fn(
        config_path="config/sonar.example.toml",
        db_path=str(tmp_path / "sonar.sqlite"),
    )

    assert result["database_path"] == str(tmp_path / "sonar.sqlite")
