"""Optional retrieval backend capability detection."""

from importlib.util import find_spec


def scrapling_available() -> bool:
    return find_spec("scrapling") is not None


def cloakbrowser_available() -> bool:
    return find_spec("cloakbrowser") is not None


def playwright_available() -> bool:
    return find_spec("playwright") is not None
