"""Embedding helpers for semantic relevance checks."""

from __future__ import annotations

import math
from dataclasses import dataclass

import httpx

from .errors import SonarBadRequestError, SonarTimeoutError, SonarUpstreamUnavailableError


@dataclass(frozen=True)
class EmbeddingSettings:
    base_url: str
    api_key: str | None
    model: str
    similarity_threshold: float
    enabled: bool = True


class EmbeddingProvider:
    def __init__(
        self,
        *,
        settings: EmbeddingSettings,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._timeout = timeout

    def embed(self, inputs: list[str]) -> list[list[float]]:
        if not inputs:
            return []
        if not self._settings.enabled:
            raise SonarBadRequestError("Embeddings provider is disabled.")

        headers = {"Content-Type": "application/json"}
        if self._settings.api_key:
            headers["Authorization"] = f"Bearer {self._settings.api_key}"

        client = httpx.Client(transport=self._transport, timeout=self._timeout)
        try:
            response = client.post(
                f"{self._settings.base_url.rstrip('/')}/embeddings",
                headers=headers,
                json={"input": inputs, "model": self._settings.model},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise SonarTimeoutError("Embedding request timed out.", timeout_seconds=self._timeout) from exc
        except httpx.HTTPError as exc:
            raise SonarUpstreamUnavailableError("Embedding request failed.") from exc
        finally:
            client.close()

        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(inputs):
            raise SonarUpstreamUnavailableError("Embedding response was malformed.", retryable=False)

        vectors: list[list[float]] = []
        for item in data:
            embedding = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(embedding, list) or not embedding:
                raise SonarUpstreamUnavailableError("Embedding response was malformed.", retryable=False)
            vectors.append([float(value) for value in embedding])
        return vectors


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)
