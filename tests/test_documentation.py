import json
import re
from pathlib import Path

from sonar.web_api import create_app


ROOT = Path(__file__).parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
NONEXISTENT_BUNDLE_ARTIFACTS = {
    "prepared_sources_bundle.md",
    "prepared_source_manifest.json",
    "source_XX.json",
}


def _markdown_files() -> list[Path]:
    return sorted(path for path in ROOT.rglob("*.md") if ".venv" not in path.parts)


def test_relative_markdown_links_resolve():
    broken: list[str] = []

    for path in _markdown_files():
        for target in MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            relative_target = target.split("#", 1)[0]
            if (
                relative_target
                and not (path.parent / relative_target).resolve().exists()
            ):
                broken.append(f"{path.relative_to(ROOT)} -> {target}")

    assert not broken, "Broken relative Markdown links:\n" + "\n".join(broken)


def test_tracked_openapi_matches_application_schema():
    tracked = json.loads((ROOT / "docs/openapi.json").read_text(encoding="utf-8"))

    assert tracked == create_app().openapi()


def test_documentation_does_not_reference_nonexistent_bundle_artifacts():
    references: list[str] = []

    for path in _markdown_files():
        text = path.read_text(encoding="utf-8")
        for artifact in NONEXISTENT_BUNDLE_ARTIFACTS:
            if artifact in text:
                references.append(f"{path.relative_to(ROOT)} -> {artifact}")

    assert not references, "Nonexistent bundle artifacts referenced:\n" + "\n".join(
        references
    )
