"""Optional CloakBrowser rendered retrieval backend."""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from urllib.parse import urlsplit

from sonar.errors import (
    SonarBodyTooLargeError,
    SonarDependencyError,
    SonarError,
    SonarUpstreamUnavailableError,
)

from ..models import RetrievalBackend
from .base import BackendResult


def retrieve_with_cloakbrowser(
    *,
    url: str,
    timeout_seconds: float,
    max_body_bytes: int,
    wait_until: str,
    validate_url: Callable[[str], None] | None = None,
) -> BackendResult:
    try:
        import cloakbrowser
    except ImportError as exc:
        raise SonarDependencyError(
            "CloakBrowser retrieval is not installed.", dependency="cloakbrowser"
        ) from exc

    started = perf_counter()
    context = None
    page = None
    try:
        context = cloakbrowser.launch_context()
        page = context.new_page()
        if validate_url:
            if not hasattr(page, "route"):
                raise SonarUpstreamUnavailableError(
                    "CloakBrowser cannot enforce retrieval policy."
                )
            requested_origin = _origin(url)

            def enforce_policy(route, request) -> None:
                try:
                    validate_url(str(request.url))
                    if (
                        request.is_navigation_request()
                        and _origin(str(request.url)) != requested_origin
                    ):
                        route.abort()
                    else:
                        route.continue_()
                except Exception:
                    route.abort()

            page.route("**/*", enforce_policy)
        response = page.goto(
            url, wait_until=wait_until, timeout=int(timeout_seconds * 1000)
        )
        if validate_url:
            validate_url(str(page.url or url))
        html = str(page.content() or "")
        body = html.encode("utf-8")
        if len(body) > max_body_bytes:
            raise SonarBodyTooLargeError(
                "Fetched document exceeded the configured body-size limit."
            )
        headers = response.headers if response is not None else {}
        return BackendResult(
            backend=RetrievalBackend.CLOAKBROWSER,
            final_url=str(page.url or url),
            status_code=response.status if response is not None else None,
            content_type=str(headers.get("content-type", "text/html"))
            .split(";")[0]
            .strip()
            .lower(),
            body=body,
            rendered=True,
            duration_ms=int((perf_counter() - started) * 1000),
        )
    except SonarError:
        raise
    except Exception as exc:
        raise SonarUpstreamUnavailableError("CloakBrowser retrieval failed.") from exc
    finally:
        for resource in (page, context):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    pass


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    return parts.scheme, parts.hostname or "", parts.port
