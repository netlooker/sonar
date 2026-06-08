"""Pure fallback assessment for HTML retrieval."""

from __future__ import annotations

from sonar.extract import ExtractArtifact

from .models import FallbackReason


BOT_RESTRICTION_MARKERS = (
    "access denied",
    "are you a robot",
    "blocked by network security",
    "captcha",
    "checking your browser",
    "cloudflare",
    "enable javascript",
    "too many requests",
    "unusual traffic",
    "verify you are human",
)


def assess_html_fallback(
    *,
    status_code: int | None,
    body: bytes | None,
    extracted: ExtractArtifact | None,
    thin_text_min_chars: int,
) -> FallbackReason | None:
    if status_code is None:
        return FallbackReason.TRANSPORT_FAILURE
    if status_code == 401:
        return FallbackReason.HTTP_401
    if status_code == 403:
        return FallbackReason.HTTP_403
    if status_code == 429:
        return FallbackReason.HTTP_429

    html = (body or b"").decode("utf-8", errors="ignore")
    text = extracted.text if extracted else ""
    haystack = f"{html}\n{text}".lower()
    if any(marker in haystack for marker in BOT_RESTRICTION_MARKERS):
        return FallbackReason.RESTRICTION_MARKER
    if _looks_like_app_shell(html, text, thin_text_min_chars):
        return FallbackReason.APP_SHELL
    if extracted is None:
        return FallbackReason.EMPTY_EXTRACTION
    if len(text.strip()) < thin_text_min_chars:
        return FallbackReason.THIN_TEXT
    return None


def _looks_like_app_shell(html: str, text: str, thin_text_min_chars: int) -> bool:
    if len(text.strip()) >= thin_text_min_chars:
        return False
    lowered = html.lower()
    root_markers = (
        'id="root"',
        "id='root'",
        'id="app"',
        "id='app'",
        "data-reactroot",
        "__next",
    )
    return lowered.count("<script") >= 3 or any(
        marker in lowered for marker in root_markers
    )
