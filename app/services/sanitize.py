"""Neutralise markup in untrusted text before it is placed inside prompt tags."""
import re

_TAG = re.compile(r"</?[A-Za-z][^>]*>")


def clean(text: str | None, limit: int | None = None) -> str:
    """Strip tag-like markup (so '</evidence>' cannot close our wrapper) and collapse whitespace."""
    t = _TAG.sub(" ", text or "")
    t = t.replace("<", "\u2039").replace(">", "\u203a")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit] if limit else t


def attr(text: str | None, limit: int = 120) -> str:
    """For values placed inside XML-style attributes."""
    return clean(text, limit).replace('"', "'")
