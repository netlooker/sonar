import json

from sonar import smoke


def test_smoke_outputs_health_json(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        "sys.argv",
        ["sonar-smoke", "--config", "config/sonar.example.toml", "--db", str(tmp_path / "sonar.sqlite")],
    )

    smoke.main()

    payload = json.loads(capsys.readouterr().out)
    assert "health" in payload
