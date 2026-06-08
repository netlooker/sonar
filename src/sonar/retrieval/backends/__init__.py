"""Retrieval backend adapters."""

from .cloakbrowser_backend import retrieve_with_cloakbrowser
from .httpx_backend import retrieve_with_httpx
from .scrapling_backend import retrieve_with_scrapling

__all__ = [
    "retrieve_with_cloakbrowser",
    "retrieve_with_httpx",
    "retrieve_with_scrapling",
]
