"""Prepared bundle persistence helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import time
from typing import Any, Mapping

from .storage import Repository


DEFAULT_BUNDLE_ROOT = Path("~/.sonar/bundles").expanduser()
ARTIFACT_FILENAME = "prepared_source_bundle.json"


def build_request_fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_bundle_id(request_fingerprint: str) -> str:
    encoded = f"{request_fingerprint}:{time()}".encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def persist_prepared_bundle(
    bundle: Mapping[str, Any],
    *,
    output_dir: str | None,
    include_sidecars: bool,
    repo: Repository | None = None,
) -> dict[str, Any]:
    payload = json.loads(json.dumps(bundle))
    bundle_id = str(payload["bundle_id"])
    bundle_dir = _resolve_bundle_dir(bundle_id=bundle_id, output_dir=output_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    for index, source in enumerate(payload.get("sources", []), start=1):
        full_text = source.get("full_text")
        full_text_path = None
        if include_sidecars and full_text:
            sidecar_name = f"source_{index:02d}.txt"
            sidecar_path = bundle_dir / sidecar_name
            sidecar_path.write_text(str(full_text), encoding="utf-8")
            full_text_path = str(sidecar_path)
        source["full_text_path"] = full_text_path

    payload["bundle_path"] = str(bundle_dir)
    manifest_path = bundle_dir / ARTIFACT_FILENAME
    _atomic_write_json(manifest_path, payload)

    if repo is not None:
        repo.store_prepared_bundle(payload)

    return payload


def _resolve_bundle_dir(*, bundle_id: str, output_dir: str | None) -> Path:
    if output_dir:
        return Path(output_dir).expanduser() / bundle_id
    return DEFAULT_BUNDLE_ROOT / bundle_id


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(json.dumps(payload, indent=2))
        tmp_path = Path(handle.name)
    tmp_path.replace(path)
