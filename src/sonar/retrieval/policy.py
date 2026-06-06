"""Unified retrieval target and backend policy."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

from sonar.errors import (
    SonarBadRequestError,
    SonarForbiddenError,
    SonarUpstreamUnavailableError,
)
from sonar.settings import AppSettings

from .models import RetrievalBackend


@dataclass(frozen=True)
class PolicyDecision:
    hostname: str
    backend: RetrievalBackend
    allowlist_matched: bool = False


def assert_backend_allowed(
    url: str,
    backend: RetrievalBackend,
    settings: AppSettings,
    *,
    resolver=socket.getaddrinfo,
) -> PolicyDecision:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise SonarBadRequestError("Retrieval URL must use HTTP or HTTPS.")

    hostname = parts.hostname.lower()
    domain = settings.domains.get(hostname)
    if domain and domain.allow is False:
        raise SonarForbiddenError("Retrieval policy denies this domain.")
    if (
        domain
        and domain.allowed_backends
        and backend.value not in domain.allowed_backends
    ):
        raise SonarForbiddenError(
            f"Retrieval policy denies backend {backend.value} for this domain."
        )
    if settings.policy.deny_local_networks and _is_local_target(
        hostname, parts.port, resolver
    ):
        raise SonarForbiddenError("Retrieval policy denies local-network targets.")
    return PolicyDecision(
        hostname=hostname,
        backend=backend,
        allowlist_matched=bool(domain and domain.allow is True),
    )


def _is_local_target(hostname: str, port: int | None, resolver) -> bool:
    if hostname in {"localhost", "localhost.localdomain"}:
        return True
    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in resolver(hostname, port or 443, type=socket.SOCK_STREAM)
            }
        except OSError as exc:
            raise SonarUpstreamUnavailableError(
                "Retrieval target DNS resolution failed."
            ) from exc
    return any(
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        for address in addresses
    )
