"""Readable-text extraction utilities."""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

from .errors import SonarBadRequestError, SonarDependencyError, SonarUpstreamUnavailableError


HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
PDF_CONTENT_TYPES = {"application/pdf"}
DOCX_CONTENT_TYPES = {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
ODT_CONTENT_TYPES = {"application/vnd.oasis.opendocument.text"}
MARKDOWN_CONTENT_TYPES = {"text/markdown", "text/x-markdown"}
TEXT_CONTENT_TYPES = {"text/plain"}
GENERIC_TEXT_CONTENT_TYPES = {"application/octet-stream", ""}


@dataclass(frozen=True)
class ExtractArtifact:
    canonical_url: str
    title: str | None
    byline: str | None
    published_at: str | None
    language: str | None
    excerpt: str | None
    abstract: str | None
    text: str
    word_count: int
    source_format: str
    extraction_method: str
    extraction_status: str


def extract_document(body: bytes, *, url: str, content_type: str | None = None) -> ExtractArtifact:
    source_format = detect_source_format(url=url, content_type=content_type)
    if source_format == "html":
        return _extract_html_document(body, url=url)
    if source_format == "pdf":
        return _extract_pdf_document(body, url=url)
    if source_format == "docx":
        return _extract_docx_document(body, url=url)
    if source_format == "odt":
        return _extract_odt_document(body, url=url)
    if source_format == "markdown":
        return _extract_markdown_document(body, url=url)
    if source_format == "text":
        return _extract_text_document(body, url=url)
    raise SonarBadRequestError(f"Unsupported extraction format for URL: {url}")


def detect_source_format(*, url: str, content_type: str | None) -> str | None:
    normalized_type = (content_type or "").split(";")[0].strip().lower()
    suffix = Path(url).suffix.lower()
    if normalized_type in HTML_CONTENT_TYPES:
        return "html"
    if normalized_type in PDF_CONTENT_TYPES:
        return "pdf"
    if normalized_type in DOCX_CONTENT_TYPES:
        return "docx"
    if normalized_type in ODT_CONTENT_TYPES:
        return "odt"
    if normalized_type in MARKDOWN_CONTENT_TYPES:
        return "markdown"
    if normalized_type in TEXT_CONTENT_TYPES:
        return "text"
    if normalized_type in GENERIC_TEXT_CONTENT_TYPES or not normalized_type:
        if suffix == ".pdf":
            return "pdf"
        if suffix == ".docx":
            return "docx"
        if suffix == ".odt":
            return "odt"
        if suffix == ".md":
            return "markdown"
        if suffix == ".txt":
            return "text"
    return None


def trafilatura_available() -> bool:
    try:
        import trafilatura  # noqa: F401
    except ImportError:
        return False
    return True


def _extract_html_document(body: bytes, *, url: str) -> ExtractArtifact:
    try:
        import trafilatura
    except ImportError as exc:  # pragma: no cover - installation path
        raise SonarDependencyError(
            "Trafilatura is required for HTML extraction.",
            dependency="trafilatura",
            retryable=False,
        ) from exc

    decoded = body.decode("utf-8", errors="ignore")
    payload = trafilatura.extract(
        decoded,
        url=url,
        with_metadata=True,
        output_format="json",
        include_comments=False,
        include_tables=False,
    )
    if not payload:
        raise SonarUpstreamUnavailableError("Readable text extraction returned no content.", retryable=False)
    parsed = json.loads(payload)
    text = str(parsed.get("text", "")).strip()
    if not text:
        raise SonarUpstreamUnavailableError("Readable text extraction returned empty text.", retryable=False)
    excerpt = _nullable_str(parsed.get("excerpt"))
    return ExtractArtifact(
        canonical_url=str(parsed.get("url", url)),
        title=_nullable_str(parsed.get("title")),
        byline=_nullable_str(parsed.get("author")),
        published_at=_nullable_str(parsed.get("date")),
        language=_nullable_str(parsed.get("language")),
        excerpt=excerpt,
        abstract=excerpt if _looks_like_abstract(excerpt) else None,
        text=text,
        word_count=len(text.split()),
        source_format="html",
        extraction_method="html",
        extraction_status=_extraction_status_for_text(text=text, title=_nullable_str(parsed.get("title"))),
    )


def _extract_pdf_document(body: bytes, *, url: str) -> ExtractArtifact:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - installation path
        raise SonarDependencyError(
            "pypdf is required for PDF extraction.",
            dependency="pypdf",
            retryable=False,
        ) from exc

    reader = PdfReader(BytesIO(body))
    texts = [(page.extract_text() or "").strip() for page in reader.pages]
    text = "\n\n".join(chunk for chunk in texts if chunk)
    if not text.strip():
        raise SonarUpstreamUnavailableError("PDF extraction returned empty text.", retryable=False)
    abstract = _extract_abstract_section(text)
    title = _nullable_str(reader.metadata.title) if reader.metadata else None
    byline = _nullable_str(reader.metadata.author) if reader.metadata else None
    return ExtractArtifact(
        canonical_url=url,
        title=title,
        byline=byline,
        published_at=None,
        language=None,
        excerpt=_build_excerpt(text),
        abstract=abstract,
        text=text,
        word_count=len(text.split()),
        source_format="pdf",
        extraction_method="pdf",
        extraction_status=_extraction_status_for_text(text=text, title=title),
    )


def _extract_docx_document(body: bytes, *, url: str) -> ExtractArtifact:
    text = _extract_zip_text(body, member="word/document.xml")
    title = _title_from_text(url=url, text=text)
    abstract = _extract_abstract_section(text)
    return ExtractArtifact(
        canonical_url=url,
        title=title,
        byline=None,
        published_at=None,
        language=None,
        excerpt=_build_excerpt(text),
        abstract=abstract,
        text=text,
        word_count=len(text.split()),
        source_format="docx",
        extraction_method="docx",
        extraction_status=_extraction_status_for_text(text=text, title=title),
    )


def _extract_odt_document(body: bytes, *, url: str) -> ExtractArtifact:
    text = _extract_zip_text(body, member="content.xml")
    title = _title_from_text(url=url, text=text)
    abstract = _extract_abstract_section(text)
    return ExtractArtifact(
        canonical_url=url,
        title=title,
        byline=None,
        published_at=None,
        language=None,
        excerpt=_build_excerpt(text),
        abstract=abstract,
        text=text,
        word_count=len(text.split()),
        source_format="odt",
        extraction_method="odt",
        extraction_status=_extraction_status_for_text(text=text, title=title),
    )


def _extract_markdown_document(body: bytes, *, url: str) -> ExtractArtifact:
    text = body.decode("utf-8", errors="ignore")
    normalized = _normalize_text(text)
    if not normalized:
        raise SonarUpstreamUnavailableError("Markdown extraction returned empty text.", retryable=False)
    title = _extract_markdown_title(text) or _title_from_text(url=url, text=normalized)
    abstract = _extract_abstract_section(normalized)
    return ExtractArtifact(
        canonical_url=url,
        title=title,
        byline=None,
        published_at=None,
        language=None,
        excerpt=_build_excerpt(normalized),
        abstract=abstract,
        text=normalized,
        word_count=len(normalized.split()),
        source_format="markdown",
        extraction_method="markdown",
        extraction_status=_extraction_status_for_text(text=normalized, title=title),
    )


def _extract_text_document(body: bytes, *, url: str) -> ExtractArtifact:
    text = _normalize_text(body.decode("utf-8", errors="ignore"))
    if not text:
        raise SonarUpstreamUnavailableError("Text extraction returned empty text.", retryable=False)
    title = _title_from_text(url=url, text=text)
    abstract = _extract_abstract_section(text)
    return ExtractArtifact(
        canonical_url=url,
        title=title,
        byline=None,
        published_at=None,
        language=None,
        excerpt=_build_excerpt(text),
        abstract=abstract,
        text=text,
        word_count=len(text.split()),
        source_format="text",
        extraction_method="text",
        extraction_status=_extraction_status_for_text(text=text, title=title),
    )


def _extract_zip_text(body: bytes, *, member: str) -> str:
    try:
        archive = zipfile.ZipFile(BytesIO(body))
    except zipfile.BadZipFile as exc:
        raise SonarUpstreamUnavailableError("Archive extraction failed.", retryable=False) from exc
    try:
        with archive.open(member) as handle:
            xml_text = handle.read().decode("utf-8", errors="ignore")
    except KeyError as exc:
        raise SonarUpstreamUnavailableError("Expected document payload was missing.", retryable=False) from exc
    root = ElementTree.fromstring(xml_text)
    fragments = []
    for text_node in root.iter():
        if text_node.text and text_node.text.strip():
            fragments.append(text_node.text.strip())
    text = _normalize_text("\n".join(fragments))
    if not text:
        raise SonarUpstreamUnavailableError("Structured document extraction returned empty text.", retryable=False)
    return text


def _extract_markdown_title(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            candidate = stripped.lstrip("#").strip()
            if candidate:
                return candidate
    return None


def _extract_abstract_section(text: str) -> str | None:
    match = re.search(
        r"(?is)\babstract\b[:\s]*([\s\S]{40,1200}?)(?:\n\s*\n|\n[A-Z][^\n]{0,80}\n|$)",
        text,
    )
    if not match:
        return None
    return _normalize_text(match.group(1)) or None


def _looks_like_abstract(value: str | None) -> bool:
    if not value:
        return False
    normalized = _normalize_text(value)
    if len(normalized.split()) < 20:
        return False
    return True


def _build_excerpt(text: str) -> str | None:
    normalized = _normalize_text(text)
    if not normalized:
        return None
    return normalized[:400]


def _title_from_text(*, url: str, text: str) -> str | None:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if first_line:
        return first_line[:200]
    stem = Path(url).stem.replace("-", " ").replace("_", " ").strip()
    return stem[:200] or None


def _normalize_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r", "\n").split("\n")]
    compact = "\n".join(line for line in lines if line)
    compact = re.sub(r"\n{3,}", "\n\n", compact)
    return compact.strip()


def _extraction_status_for_text(*, text: str, title: str | None) -> str:
    words = len(text.split())
    if words >= 100 and title:
        return "full"
    if words >= 20:
        return "partial"
    return "failed"


def _nullable_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
