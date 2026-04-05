from pathlib import Path


SUSPICIOUS_STRINGS = [
    "/Users/",
    "outlook.be",
    "tail839ce7",
    "tvly-",
    "192.168.",
]


def test_gitignore_covers_local_config_and_secrets():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "config/sonar.toml" in gitignore
    assert "secrets/*" in gitignore
    assert ".env" in gitignore


def test_tracked_example_files_are_placeholder_only():
    tracked_files = [
        Path("config/sonar.example.toml"),
        Path("secrets/README.md"),
        Path("secrets/sonar.secrets.example.toml"),
        Path("README.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in tracked_files)

    for text in SUSPICIOUS_STRINGS:
        assert text not in combined
