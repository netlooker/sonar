import asyncio
import socket
import sys
from types import ModuleType

import httpx
import pytest

from sonar.errors import (
    SonarBadRequestError,
    SonarBodyTooLargeError,
    SonarDependencyError,
    SonarForbiddenError,
    SonarRobotsUnavailableError,
    SonarTimeoutError,
    SonarUpstreamUnavailableError,
)
from sonar.retrieval.backends.cloakbrowser_backend import retrieve_with_cloakbrowser
from sonar.retrieval.backends.httpx_backend import retrieve_with_httpx
from sonar.retrieval.backends.scrapling_backend import retrieve_with_scrapling
from sonar.retrieval.heuristics import assess_html_fallback
from sonar.retrieval.backends.base import BackendResult
from sonar.retrieval.models import FallbackReason, RetrievalBackend
from sonar.retrieval.orchestrator import retrieve_url
from sonar.retrieval.policy import assert_backend_allowed
from sonar.retrieval.robots import assert_allowed_by_robots
from sonar.settings import (
    AppSettings,
    DomainPolicySettings,
    FetchSettings,
    PolicySettings,
    RetrievalSettings,
)


def test_policy_blocks_literal_and_dns_resolved_local_targets():
    settings = AppSettings(policy=PolicySettings(deny_local_networks=True))

    with pytest.raises(SonarForbiddenError):
        assert_backend_allowed("http://127.0.0.1/page", RetrievalBackend.HTTP, settings)

    def local_resolver(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 443))]

    with pytest.raises(SonarForbiddenError):
        assert_backend_allowed(
            "https://internal.example/page",
            RetrievalBackend.HTTP,
            settings,
            resolver=local_resolver,
        )


def test_policy_evaluates_each_backend_independently():
    settings = AppSettings(
        policy=PolicySettings(deny_local_networks=False),
        domains={"example.com": DomainPolicySettings(allowed_backends=("http",))},
    )

    assert_backend_allowed("https://example.com/page", RetrievalBackend.HTTP, settings)
    with pytest.raises(SonarForbiddenError):
        assert_backend_allowed(
            "https://example.com/page", RetrievalBackend.CLOAKBROWSER, settings
        )


def test_policy_rejects_invalid_denied_and_unresolvable_targets():
    settings = AppSettings(
        domains={"blocked.example": DomainPolicySettings(allow=False)}
    )

    with pytest.raises(SonarBadRequestError):
        assert_backend_allowed("file:///tmp/page", RetrievalBackend.HTTP, settings)
    with pytest.raises(SonarForbiddenError, match="denies this domain"):
        assert_backend_allowed(
            "https://blocked.example/page", RetrievalBackend.HTTP, settings
        )
    with pytest.raises(SonarUpstreamUnavailableError, match="DNS resolution"):
        assert_backend_allowed(
            "https://missing.example/page",
            RetrievalBackend.HTTP,
            settings,
            resolver=lambda *args, **kwargs: (_ for _ in ()).throw(
                socket.gaierror("not found")
            ),
        )


def test_robots_transport_and_site_denial_are_terminal():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(
                httpx.ConnectError("failed", request=request)
            )
        )
    ) as client:
        with pytest.raises(SonarRobotsUnavailableError):
            assert_allowed_by_robots(client, "https://example.com/page", "Sonar")

    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(403))
    ) as client:
        with pytest.raises(SonarForbiddenError, match="site"):
            assert_allowed_by_robots(client, "https://example.com/page", "Sonar")


def test_scrapling_backend_disables_redirects(monkeypatch):
    calls = []

    class FakeFetcher:
        @staticmethod
        def get(url, **kwargs):
            calls.append((url, kwargs))
            return type(
                "Page",
                (),
                {
                    "body": b"",
                    "headers": {"location": "http://127.0.0.1/private"},
                    "url": url,
                    "status": 302,
                },
            )()

    scrapling = ModuleType("scrapling")
    fetchers = ModuleType("scrapling.fetchers")
    fetchers.Fetcher = FakeFetcher
    monkeypatch.setitem(sys.modules, "scrapling", scrapling)
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", fetchers)

    with pytest.raises(SonarUpstreamUnavailableError, match="unvalidated redirect"):
        retrieve_with_scrapling(
            url="https://example.com/page",
            timeout_seconds=2,
            max_body_bytes=1024,
        )

    assert calls[0][1]["follow_redirects"] is False


def test_optional_backends_report_missing_dependencies(monkeypatch):
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", None)
    monkeypatch.setitem(sys.modules, "cloakbrowser", None)

    with pytest.raises(SonarDependencyError, match="Scrapling"):
        retrieve_with_scrapling(
            url="https://example.com/page",
            timeout_seconds=2,
            max_body_bytes=1024,
        )

    with pytest.raises(SonarDependencyError, match="CloakBrowser"):
        retrieve_with_cloakbrowser(
            url="https://example.com/page",
            timeout_seconds=2,
            max_body_bytes=1024,
            wait_until="domcontentloaded",
        )


def test_scrapling_backend_enforces_body_limit_and_wraps_failures(monkeypatch):
    class FakeFetcher:
        @staticmethod
        def get(url, **kwargs):
            if url.endswith("/failure"):
                raise RuntimeError("failed")
            return type("Page", (), {"body": b"too large", "status": 200})()

    fetchers = ModuleType("scrapling.fetchers")
    fetchers.Fetcher = FakeFetcher
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", fetchers)

    with pytest.raises(SonarBodyTooLargeError):
        retrieve_with_scrapling(
            url="https://example.com/page",
            timeout_seconds=2,
            max_body_bytes=3,
        )

    with pytest.raises(SonarUpstreamUnavailableError, match="Scrapling HTTP"):
        retrieve_with_scrapling(
            url="https://example.com/failure",
            timeout_seconds=2,
            max_body_bytes=1024,
        )


def test_cloakbrowser_requires_policy_routing_support(monkeypatch):
    closed = []

    class FakePage:
        def close(self):
            closed.append("page")

    class FakeContext:
        def new_page(self):
            return FakePage()

        def close(self):
            closed.append("context")

    cloakbrowser = ModuleType("cloakbrowser")
    cloakbrowser.launch_context = lambda: FakeContext()
    monkeypatch.setitem(sys.modules, "cloakbrowser", cloakbrowser)

    with pytest.raises(
        SonarUpstreamUnavailableError, match="cannot enforce retrieval policy"
    ):
        retrieve_with_cloakbrowser(
            url="https://example.com/page",
            timeout_seconds=2,
            max_body_bytes=1024,
            wait_until="domcontentloaded",
            validate_url=lambda url: None,
        )

    assert closed == ["page", "context"]


def test_cloakbrowser_blocks_cross_origin_navigation_before_request(monkeypatch):
    route_outcomes = []

    class FakeRoute:
        def abort(self):
            route_outcomes.append("aborted")

        def continue_(self):
            route_outcomes.append("continued")

    class FakeRequest:
        url = "https://other.example/redirected"

        @staticmethod
        def is_navigation_request():
            return True

    class FakePage:
        url = "https://example.com/page"

        def route(self, pattern, callback):
            self.callback = callback

        def goto(self, *args, **kwargs):
            self.callback(FakeRoute(), FakeRequest())
            raise RuntimeError("navigation aborted")

        def close(self):
            pass

    class FakeContext:
        def new_page(self):
            return FakePage()

        def close(self):
            pass

    cloakbrowser = ModuleType("cloakbrowser")
    cloakbrowser.launch_context = lambda: FakeContext()
    monkeypatch.setitem(sys.modules, "cloakbrowser", cloakbrowser)

    with pytest.raises(
        SonarUpstreamUnavailableError, match="CloakBrowser retrieval failed"
    ):
        retrieve_with_cloakbrowser(
            url="https://example.com/page",
            timeout_seconds=2,
            max_body_bytes=1024,
            wait_until="domcontentloaded",
            validate_url=lambda url: None,
        )

    assert route_outcomes == ["aborted"]


def test_cloakbrowser_blocks_denied_subresource_and_returns_page(monkeypatch):
    route_outcomes = []
    validated = []

    class FakeRoute:
        def abort(self):
            route_outcomes.append("aborted")

        def continue_(self):
            route_outcomes.append("continued")

    class FakeRequest:
        url = "http://127.0.0.1/private.js"

        @staticmethod
        def is_navigation_request():
            return False

    class FakeResponse:
        status = 200
        headers = {"content-type": "text/html; charset=utf-8"}

    class FakePage:
        url = "https://example.com/page"

        def route(self, pattern, callback):
            self.callback = callback

        def goto(self, *args, **kwargs):
            self.callback(FakeRoute(), FakeRequest())
            return FakeResponse()

        def content(self):
            return "<html><article>rendered page</article></html>"

        def close(self):
            pass

    class FakeContext:
        def new_page(self):
            return FakePage()

        def close(self):
            pass

    cloakbrowser = ModuleType("cloakbrowser")
    cloakbrowser.launch_context = lambda: FakeContext()
    monkeypatch.setitem(sys.modules, "cloakbrowser", cloakbrowser)

    def validate(url):
        validated.append(url)
        if url.startswith("http://127."):
            raise SonarForbiddenError("denied")

    result = retrieve_with_cloakbrowser(
        url="https://example.com/page",
        timeout_seconds=2,
        max_body_bytes=1024,
        wait_until="domcontentloaded",
        validate_url=validate,
    )

    assert route_outcomes == ["aborted"]
    assert validated == ["http://127.0.0.1/private.js", "https://example.com/page"]
    assert result.rendered is True
    assert result.content_type == "text/html"


def test_cloakbrowser_enforces_body_limit(monkeypatch):
    class FakePage:
        url = "https://example.com/page"

        def goto(self, *args, **kwargs):
            return None

        def content(self):
            return "<html>too large</html>"

        def close(self):
            pass

    class FakeContext:
        def new_page(self):
            return FakePage()

        def close(self):
            pass

    cloakbrowser = ModuleType("cloakbrowser")
    cloakbrowser.launch_context = lambda: FakeContext()
    monkeypatch.setitem(sys.modules, "cloakbrowser", cloakbrowser)

    with pytest.raises(SonarBodyTooLargeError):
        retrieve_with_cloakbrowser(
            url="https://example.com/page",
            timeout_seconds=2,
            max_body_bytes=3,
            wait_until="domcontentloaded",
        )


def test_cloakbrowser_runs_outside_callers_asyncio_event_loop(monkeypatch):
    class FakeResponse:
        status = 200
        headers = {"content-type": "text/html"}

    class FakePage:
        url = "https://example.com/page"

        def goto(self, *args, **kwargs):
            with pytest.raises(RuntimeError):
                asyncio.get_running_loop()
            return FakeResponse()

        def content(self):
            return "<html><article>rendered</article></html>"

        def close(self):
            pass

    class FakeContext:
        def new_page(self):
            return FakePage()

        def close(self):
            pass

    cloakbrowser = ModuleType("cloakbrowser")
    cloakbrowser.launch_context = lambda: FakeContext()
    monkeypatch.setitem(sys.modules, "cloakbrowser", cloakbrowser)

    async def retrieve():
        return retrieve_with_cloakbrowser(
            url="https://example.com/page",
            timeout_seconds=2,
            max_body_bytes=1024,
            wait_until="domcontentloaded",
        )

    result = asyncio.run(retrieve())

    assert result.backend is RetrievalBackend.CLOAKBROWSER
    assert result.rendered is True


def test_http_backend_reports_timeout_and_redirect_errors():
    def timeout_handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(SonarTimeoutError):
        retrieve_with_httpx(
            url="https://example.com/page",
            user_agent="Sonar",
            connect_timeout_seconds=1,
            read_timeout_seconds=1,
            max_body_bytes=1024,
            respect_robots=False,
            transport=httpx.MockTransport(timeout_handler),
        )

    with pytest.raises(SonarUpstreamUnavailableError, match="omitted a location"):
        retrieve_with_httpx(
            url="https://example.com/page",
            user_agent="Sonar",
            connect_timeout_seconds=1,
            read_timeout_seconds=1,
            max_body_bytes=1024,
            respect_robots=False,
            transport=httpx.MockTransport(lambda request: httpx.Response(302)),
        )

    with pytest.raises(SonarUpstreamUnavailableError, match="redirect limit"):
        retrieve_with_httpx(
            url="https://example.com/page",
            user_agent="Sonar",
            connect_timeout_seconds=1,
            read_timeout_seconds=1,
            max_body_bytes=1024,
            respect_robots=False,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(302, headers={"location": "/page"})
            ),
        )


def test_fallback_assessment_detects_restriction_and_app_shell():
    restriction = assess_html_fallback(
        status_code=200,
        body=b"<html>Please verify you are human</html>",
        extracted=None,
        thin_text_min_chars=200,
    )
    shell = assess_html_fallback(
        status_code=200,
        body=b'<html><div id="root"></div><script></script><script></script><script></script></html>',
        extracted=None,
        thin_text_min_chars=200,
    )

    assert restriction is FallbackReason.RESTRICTION_MARKER
    assert shell is FallbackReason.APP_SHELL


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, FallbackReason.HTTP_401),
        (403, FallbackReason.HTTP_403),
        (429, FallbackReason.HTTP_429),
    ],
)
def test_fallback_assessment_detects_access_statuses(status_code, expected):
    assert (
        assess_html_fallback(
            status_code=status_code,
            body=b"",
            extracted=None,
            thin_text_min_chars=200,
        )
        is expected
    )


def test_good_html_stays_on_http_backend():
    long_text = "Useful article content " * 30

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(
            200,
            text=f"<html><body><article>{long_text}</article></body></html>",
            headers={"content-type": "text/html"},
        )

    artifact = retrieve_url(
        url="https://example.com/page",
        settings=AppSettings(policy=PolicySettings(deny_local_networks=False)),
        transport=httpx.MockTransport(handler),
    )

    assert artifact.backend is RetrievalBackend.HTTP
    assert [attempt.backend for attempt in artifact.attempts] == [RetrievalBackend.HTTP]
    assert artifact.fallback_reason is None


def test_thin_html_reports_when_fallback_is_not_enabled():
    artifact = retrieve_url(
        url="https://example.com/page",
        settings=AppSettings(policy=PolicySettings(deny_local_networks=False)),
        transport=httpx.MockTransport(
            lambda request: (
                httpx.Response(404)
                if request.url.path == "/robots.txt"
                else httpx.Response(
                    200,
                    text="<html><article>" + ("useful " * 10) + "</article></html>",
                    headers={"content-type": "text/html"},
                )
            )
        ),
    )

    assert artifact.backend is RetrievalBackend.HTTP
    assert artifact.warnings == ("thin_text_fallback_not_available",)


def test_non_html_never_invokes_optional_fallback(monkeypatch):
    monkeypatch.setattr(
        "sonar.retrieval.orchestrator.retrieve_with_scrapling",
        lambda **kwargs: pytest.fail("Scrapling must not run for plain text"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200, text="plain document", headers={"content-type": "text/plain"}
        )

    artifact = retrieve_url(
        url="https://example.com/document.txt",
        settings=AppSettings(
            policy=PolicySettings(deny_local_networks=False),
            retrieval=RetrievalSettings(scrapling_enabled=True),
        ),
        transport=httpx.MockTransport(handler),
    )

    assert artifact.source_format == "text"
    assert [attempt.backend for attempt in artifact.attempts] == [RetrievalBackend.HTTP]


def test_pdf_transport_failure_never_invokes_optional_fallback(monkeypatch):
    monkeypatch.setattr(
        "sonar.retrieval.orchestrator.retrieve_with_scrapling",
        lambda **kwargs: pytest.fail("Scrapling must not run for a PDF URL"),
    )

    with pytest.raises(SonarUpstreamUnavailableError):
        retrieve_url(
            url="https://example.com/document.pdf",
            settings=AppSettings(
                policy=PolicySettings(deny_local_networks=False),
                retrieval=RetrievalSettings(scrapling_enabled=True),
            ),
            transport=httpx.MockTransport(
                lambda request: (
                    httpx.Response(404)
                    if request.url.path == "/robots.txt"
                    else (_ for _ in ()).throw(
                        httpx.ConnectError("failed", request=request)
                    )
                )
            ),
        )


def test_pdf_url_with_html_block_page_never_invokes_optional_fallback(monkeypatch):
    monkeypatch.setattr(
        "sonar.retrieval.orchestrator.retrieve_with_scrapling",
        lambda **kwargs: pytest.fail("Scrapling must not run for a PDF URL"),
    )

    artifact = retrieve_url(
        url="https://example.com/document.pdf",
        settings=AppSettings(
            policy=PolicySettings(deny_local_networks=False),
            retrieval=RetrievalSettings(scrapling_enabled=True),
        ),
        transport=httpx.MockTransport(
            lambda request: (
                httpx.Response(404)
                if request.url.path == "/robots.txt"
                else httpx.Response(
                    200,
                    text="<html>Please verify you are human</html>",
                    headers={"content-type": "text/html"},
                )
            )
        ),
    )

    assert artifact.backend is RetrievalBackend.HTTP
    assert artifact.source_format == "html"


def test_http_403_without_content_type_can_fallback(monkeypatch):
    monkeypatch.setattr(
        "sonar.retrieval.orchestrator.retrieve_with_scrapling",
        lambda **kwargs: BackendResult(
            backend=RetrievalBackend.SCRAPLING_HTTP,
            final_url=kwargs["url"],
            status_code=200,
            content_type="text/html",
            body=(
                "<html><body><article>" + ("useful " * 100) + "</article></body></html>"
            ).encode(),
            rendered=False,
            duration_ms=1,
        ),
    )

    artifact = retrieve_url(
        url="https://example.com/page",
        settings=AppSettings(
            policy=PolicySettings(deny_local_networks=False),
            retrieval=RetrievalSettings(scrapling_enabled=True),
        ),
        transport=httpx.MockTransport(
            lambda request: (
                httpx.Response(404)
                if request.url.path == "/robots.txt"
                else httpx.Response(403, text="blocked")
            )
        ),
    )

    assert artifact.backend is RetrievalBackend.SCRAPLING_HTTP
    assert artifact.warnings == ("http_403_triggered_scrapling_http_fallback",)


@pytest.mark.parametrize(
    ("status_code", "body", "expected_reason"),
    [
        (401, b"unauthorized", FallbackReason.HTTP_401),
        (429, b"rate limited", FallbackReason.HTTP_429),
        (
            200,
            b"<html>Please verify you are human</html>",
            FallbackReason.RESTRICTION_MARKER,
        ),
        (
            200,
            b'<html><div id="root"></div><script></script><script></script><script></script></html>',
            FallbackReason.APP_SHELL,
        ),
        (200, b"<html><body></body></html>", FallbackReason.EMPTY_EXTRACTION),
    ],
)
def test_access_and_html_markers_trigger_scrapling_fallback(
    monkeypatch, status_code, body, expected_reason
):
    monkeypatch.setattr(
        "sonar.retrieval.orchestrator.retrieve_with_scrapling",
        lambda **kwargs: BackendResult(
            backend=RetrievalBackend.SCRAPLING_HTTP,
            final_url=kwargs["url"],
            status_code=200,
            content_type="text/html",
            body=(
                "<html><body><article><p>"
                + ("Useful fallback article content. " * 100)
                + "</p></article></body></html>"
            ).encode(),
            rendered=False,
            duration_ms=1,
        ),
    )

    artifact = retrieve_url(
        url="https://example.com/page",
        settings=AppSettings(
            policy=PolicySettings(deny_local_networks=False),
            retrieval=RetrievalSettings(scrapling_enabled=True),
        ),
        transport=httpx.MockTransport(
            lambda request: (
                httpx.Response(404)
                if request.url.path == "/robots.txt"
                else httpx.Response(
                    status_code, content=body, headers={"content-type": "text/html"}
                )
            )
        ),
    )

    assert artifact.backend is RetrievalBackend.SCRAPLING_HTTP
    assert artifact.fallback_reason is expected_reason


def test_transport_failure_triggers_scrapling_fallback(monkeypatch):
    monkeypatch.setattr(
        "sonar.retrieval.orchestrator.retrieve_with_scrapling",
        lambda **kwargs: BackendResult(
            backend=RetrievalBackend.SCRAPLING_HTTP,
            final_url=kwargs["url"],
            status_code=200,
            content_type="text/html",
            body=("<article>" + ("useful " * 100) + "</article>").encode(),
            rendered=False,
            duration_ms=1,
        ),
    )

    artifact = retrieve_url(
        url="https://example.com/page",
        settings=AppSettings(
            policy=PolicySettings(deny_local_networks=False, respect_robots=False),
            retrieval=RetrievalSettings(scrapling_enabled=True),
        ),
        transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(
                httpx.ConnectError("failed", request=request)
            )
        ),
    )

    assert artifact.backend is RetrievalBackend.SCRAPLING_HTTP
    assert artifact.fallback_reason is FallbackReason.TRANSPORT_FAILURE
    assert artifact.attempts[0].outcome == "failed"


def test_missing_scrapling_dependency_can_escalate_to_browser(monkeypatch):
    monkeypatch.setattr(
        "sonar.retrieval.orchestrator.retrieve_with_scrapling",
        lambda **kwargs: (_ for _ in ()).throw(
            SonarDependencyError("Scrapling is unavailable.", dependency="scrapling")
        ),
    )
    monkeypatch.setattr(
        "sonar.retrieval.orchestrator.retrieve_with_cloakbrowser",
        lambda **kwargs: BackendResult(
            backend=RetrievalBackend.CLOAKBROWSER,
            final_url=kwargs["url"],
            status_code=200,
            content_type="text/html",
            body=(
                "<html><body><article><p>"
                + ("Rendered fallback content. " * 100)
                + "</p></article></body></html>"
            ).encode(),
            rendered=True,
            duration_ms=1,
        ),
    )

    artifact = retrieve_url(
        url="https://example.com/page",
        settings=AppSettings(
            policy=PolicySettings(deny_local_networks=False),
            retrieval=RetrievalSettings(
                scrapling_enabled=True,
                browser_enabled=True,
                cloakbrowser_enabled=True,
            ),
        ),
        transport=httpx.MockTransport(
            lambda request: (
                httpx.Response(404)
                if request.url.path == "/robots.txt"
                else httpx.Response(
                    200,
                    text="<html><body>thin</body></html>",
                    headers={"content-type": "text/html"},
                )
            )
        ),
    )

    assert artifact.backend is RetrievalBackend.CLOAKBROWSER
    assert [attempt.outcome for attempt in artifact.attempts] == [
        "retrieved",
        "failed",
        "retrieved",
    ]
    assert "scrapling_http_failed" in artifact.warnings


def test_robots_denial_never_invokes_fallback(monkeypatch):
    monkeypatch.setattr(
        "sonar.retrieval.orchestrator.retrieve_with_scrapling",
        lambda **kwargs: pytest.fail("Scrapling must not run after robots denial"),
    )

    with pytest.raises(SonarForbiddenError):
        retrieve_url(
            url="https://example.com/page",
            settings=AppSettings(
                policy=PolicySettings(deny_local_networks=False),
                retrieval=RetrievalSettings(scrapling_enabled=True),
            ),
            transport=httpx.MockTransport(
                lambda request: (
                    httpx.Response(200, text="User-agent: *\nDisallow: /\n")
                    if request.url.path == "/robots.txt"
                    else httpx.Response(200, text="page")
                )
            ),
        )


def test_robots_redirect_never_invokes_fallback(monkeypatch):
    monkeypatch.setattr(
        "sonar.retrieval.orchestrator.retrieve_with_scrapling",
        lambda **kwargs: pytest.fail(
            "Scrapling must not run when robots policy is unresolved"
        ),
    )

    with pytest.raises(
        SonarUpstreamUnavailableError, match="robots.txt request failed"
    ):
        retrieve_url(
            url="https://example.com/page",
            settings=AppSettings(
                policy=PolicySettings(deny_local_networks=False),
                retrieval=RetrievalSettings(scrapling_enabled=True),
            ),
            transport=httpx.MockTransport(
                lambda request: (
                    httpx.Response(302, headers={"location": "/other-robots.txt"})
                    if request.url.path == "/robots.txt"
                    else httpx.Response(200, text="<html>page</html>")
                )
            ),
        )


def test_body_size_limit_never_invokes_fallback(monkeypatch):
    monkeypatch.setattr(
        "sonar.retrieval.orchestrator.retrieve_with_scrapling",
        lambda **kwargs: pytest.fail(
            "Scrapling must not run after a body-size rejection"
        ),
    )

    with pytest.raises(SonarBodyTooLargeError):
        retrieve_url(
            url="https://example.com/page",
            settings=AppSettings(
                fetch=FetchSettings(max_body_bytes=10),
                policy=PolicySettings(deny_local_networks=False),
                retrieval=RetrievalSettings(scrapling_enabled=True),
            ),
            transport=httpx.MockTransport(
                lambda request: (
                    httpx.Response(404)
                    if request.url.path == "/robots.txt"
                    else httpx.Response(
                        200,
                        content=b"<html>too large</html>",
                        headers={"content-type": "text/html"},
                    )
                )
            ),
        )


def test_http_error_without_successful_fallback_is_error():
    with pytest.raises(SonarUpstreamUnavailableError):
        retrieve_url(
            url="https://example.com/page",
            settings=AppSettings(policy=PolicySettings(deny_local_networks=False)),
            transport=httpx.MockTransport(
                lambda request: (
                    httpx.Response(404)
                    if request.url.path == "/robots.txt"
                    else httpx.Response(
                        403, text="blocked", headers={"content-type": "text/html"}
                    )
                )
            ),
        )


def test_http_redirect_rechecks_policy_before_following():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    with pytest.raises(SonarForbiddenError):
        retrieve_url(
            url="https://example.com/page",
            settings=AppSettings(policy=PolicySettings(deny_local_networks=True)),
            transport=httpx.MockTransport(handler),
        )

    assert "http://127.0.0.1/private" not in calls


def test_thin_http_escalates_through_scrapling_to_browser(monkeypatch):
    long_text = "Rendered useful content " * 30
    calls = []

    def scrapling(**kwargs):
        calls.append("scrapling_http")
        return BackendResult(
            backend=RetrievalBackend.SCRAPLING_HTTP,
            final_url=kwargs["url"],
            status_code=200,
            content_type="text/html",
            body=b"<html><body>still thin</body></html>",
            rendered=False,
            duration_ms=1,
        )

    def browser(**kwargs):
        calls.append("cloakbrowser")
        return BackendResult(
            backend=RetrievalBackend.CLOAKBROWSER,
            final_url=kwargs["url"],
            status_code=200,
            content_type="text/html",
            body=f"<html><article>{long_text}</article></html>".encode(),
            rendered=True,
            duration_ms=2,
        )

    monkeypatch.setattr(
        "sonar.retrieval.orchestrator.retrieve_with_scrapling", scrapling
    )
    monkeypatch.setattr(
        "sonar.retrieval.orchestrator.retrieve_with_cloakbrowser", browser
    )

    artifact = retrieve_url(
        url="https://example.com/page",
        settings=AppSettings(
            policy=PolicySettings(deny_local_networks=False),
            retrieval=RetrievalSettings(
                scrapling_enabled=True, browser_enabled=True, cloakbrowser_enabled=True
            ),
        ),
        transport=httpx.MockTransport(
            lambda request: (
                httpx.Response(404)
                if request.url.path == "/robots.txt"
                else httpx.Response(
                    200,
                    text="<html><body>thin</body></html>",
                    headers={"content-type": "text/html"},
                )
            )
        ),
    )

    assert calls == ["scrapling_http", "cloakbrowser"]
    assert artifact.backend is RetrievalBackend.CLOAKBROWSER
    assert artifact.rendered is True
    assert artifact.fallback_reason is FallbackReason.THIN_TEXT
    assert artifact.warnings == (
        "thin_text_triggered_scrapling_http_fallback",
        "thin_text_triggered_cloakbrowser_fallback",
    )
    assert [attempt.backend for attempt in artifact.attempts] == [
        RetrievalBackend.HTTP,
        RetrievalBackend.SCRAPLING_HTTP,
        RetrievalBackend.CLOAKBROWSER,
    ]


def test_fallback_starts_from_policy_validated_http_final_url(monkeypatch):
    received = []

    def scrapling(**kwargs):
        received.append(kwargs["url"])
        return BackendResult(
            backend=RetrievalBackend.SCRAPLING_HTTP,
            final_url=kwargs["url"],
            status_code=200,
            content_type="text/html",
            body=("<article>" + ("useful " * 100) + "</article>").encode(),
            rendered=False,
            duration_ms=1,
        )

    monkeypatch.setattr(
        "sonar.retrieval.orchestrator.retrieve_with_scrapling", scrapling
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/blocked"})
        return httpx.Response(
            403, text="blocked", headers={"content-type": "text/html"}
        )

    artifact = retrieve_url(
        url="https://example.com/start",
        settings=AppSettings(
            policy=PolicySettings(deny_local_networks=False),
            retrieval=RetrievalSettings(scrapling_enabled=True),
        ),
        transport=httpx.MockTransport(handler),
    )

    assert received == ["https://example.com/blocked"]
    assert artifact.backend is RetrievalBackend.SCRAPLING_HTTP


def test_policy_denial_from_optional_backend_is_terminal(monkeypatch):
    def scrapling(**kwargs):
        kwargs["validate_url"]("http://127.0.0.1/private")
        pytest.fail("Policy validation must raise before returning")

    monkeypatch.setattr(
        "sonar.retrieval.orchestrator.retrieve_with_scrapling", scrapling
    )
    monkeypatch.setattr(
        "sonar.retrieval.orchestrator.retrieve_with_cloakbrowser",
        lambda **kwargs: pytest.fail("Browser must not run after policy denial"),
    )

    with pytest.raises(SonarForbiddenError):
        retrieve_url(
            url="https://example.com/page",
            settings=AppSettings(
                retrieval=RetrievalSettings(
                    scrapling_enabled=True,
                    browser_enabled=True,
                    cloakbrowser_enabled=True,
                ),
            ),
            transport=httpx.MockTransport(
                lambda request: (
                    httpx.Response(404)
                    if request.url.path == "/robots.txt"
                    else httpx.Response(
                        200,
                        text="<html>thin</html>",
                        headers={"content-type": "text/html"},
                    )
                )
            ),
        )


def test_later_backend_failure_returns_earlier_usable_result(monkeypatch):
    def fail(**kwargs):
        raise SonarUpstreamUnavailableError("Scrapling failed.")

    monkeypatch.setattr("sonar.retrieval.orchestrator.retrieve_with_scrapling", fail)

    artifact = retrieve_url(
        url="https://example.com/page",
        settings=AppSettings(
            policy=PolicySettings(deny_local_networks=False),
            retrieval=RetrievalSettings(scrapling_enabled=True),
        ),
        transport=httpx.MockTransport(
            lambda request: (
                httpx.Response(404)
                if request.url.path == "/robots.txt"
                else httpx.Response(
                    200,
                    text="<html><body>thin but usable</body></html>",
                    headers={"content-type": "text/html"},
                )
            )
        ),
    )

    assert artifact.backend is RetrievalBackend.HTTP
    assert artifact.warnings == (
        "thin_text_triggered_scrapling_http_fallback",
        "scrapling_http_failed",
    )
