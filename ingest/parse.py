"""Pure parsing helpers for the ingester (stdlib only, so they are easy to test)."""
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    dt = None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(el: ET.Element, *names: str) -> str:
    for child in el:
        if _local(child.tag) in names and (child.text or "").strip():
            return child.text.strip()
    return ""


def parse_feed(xml_text: str) -> dict:
    """RSS, Atom, sitemap or sitemap index -> {"kind": ..., "entries": [{"url", "date"}]}.
    Documents with a DOCTYPE/ENTITY are rejected (entity-expansion attacks); real feeds do not need them."""
    low = (xml_text or "").lower()
    if "<!doctype" in low or "<!entity" in low:
        return {"kind": "invalid", "entries": []}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {"kind": "invalid", "entries": []}

    kind = _local(root.tag).lower()
    entries: list[dict] = []
    if kind == "rss" or kind == "rdf":
        for el in root.iter():
            if _local(el.tag) == "item":
                url = _child_text(el, "link")
                if url:
                    entries.append({"url": url, "date": _child_text(el, "pubDate", "date", "updated")})
    elif kind == "feed":
        for el in root:
            if _local(el.tag) == "entry":
                href = ""
                for link in el:
                    if _local(link.tag) == "link" and link.get("rel", "alternate") == "alternate" and link.get("href"):
                        href = link.get("href")
                        break
                if href:
                    entries.append({"url": href, "date": _child_text(el, "updated", "published")})
    elif kind in ("urlset", "sitemapindex"):
        wanted = "url" if kind == "urlset" else "sitemap"
        for el in root:
            if _local(el.tag) == wanted:
                loc = _child_text(el, "loc")
                if loc:
                    entries.append({"url": loc, "date": _child_text(el, "lastmod")})
    else:
        return {"kind": "invalid", "entries": []}
    return {"kind": kind, "entries": entries}


_LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
_ATTR = re.compile(r"([\w:-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")


def discover_feeds(html: str, base_url: str) -> list[str]:
    """Find <link rel="alternate" type="application/rss+xml|atom+xml"> feeds advertised by a page."""
    found: list[str] = []
    for tag in _LINK_TAG.findall(html or ""):
        attrs = {m[0].lower(): (m[1] or m[2]) for m in _ATTR.findall(tag)}
        if "alternate" in attrs.get("rel", "").lower() and re.search(r"application/(rss|atom)\+xml", attrs.get("type", ""), re.I):
            href = attrs.get("href")
            if href:
                found.append(urljoin(base_url, href))
    return list(dict.fromkeys(found))


def sitemaps_from_robots(robots_txt: str) -> list[str]:
    return [line.split(":", 1)[1].strip() for line in (robots_txt or "").splitlines()
            if line.lower().startswith("sitemap:") and line.split(":", 1)[1].strip()]


# ---------- ClaimReview (schema.org) extraction

_LD_JSON = re.compile(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.I | re.S)


def _walk(node):
    if isinstance(node, list):
        for x in node:
            yield from _walk(x)
    elif isinstance(node, dict):
        yield node
        for v in node.values():
            if isinstance(v, (dict, list)):
                yield from _walk(v)


def _text(v) -> str:
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list) and v:
        return _text(v[0])
    if isinstance(v, dict):
        return _text(v.get("name", ""))
    return ""


def _is_claim_review(d: dict) -> bool:
    t = d.get("@type")
    types = t if isinstance(t, list) else [t]
    return any(isinstance(x, str) and x.endswith("ClaimReview") for x in types)


def _host(url: str) -> str:
    h = (urlsplit(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def extract_claim_reviews(html: str, page_url: str) -> list[dict]:
    """Returns [{"claim","rating","publisher","url","date","lang"}] from the page's JSON-LD blocks."""
    out: list[dict] = []
    for raw in _LD_JSON.findall(html or ""):
        try:
            data = json.loads(raw.strip(), strict=False)
        except ValueError:
            continue
        for d in _walk(data):
            if not _is_claim_review(d):
                continue
            rr = d.get("reviewRating")
            rr = rr[0] if isinstance(rr, list) and rr else rr
            rating = ""
            if isinstance(rr, dict):
                rating = _text(rr.get("alternateName")) or _text(rr.get("name"))
                if not rating:
                    rv = _text(rr.get("ratingValue"))
                    rating = rv if rv and not rv.replace(".", "").isdigit() else ""
            claim = _text(d.get("claimReviewed")) or _text(d.get("itemReviewed"))
            if not claim or not rating:
                continue
            url = _text(d.get("url"))
            if not url.startswith("http") or _host(url) != _host(page_url):
                url = page_url      # never trust a cross-site URL claimed by the page
            lang = d.get("inLanguage")
            out.append({"claim": claim, "rating": rating, "publisher": _text(d.get("author")) or _text(d.get("publisher")),
                        "url": url, "date": _text(d.get("datePublished")) or _text(d.get("dateModified")),
                        "lang": lang if isinstance(lang, str) else ""})
    return out
