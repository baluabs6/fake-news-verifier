"""Simple source-credibility score: domain reputation table + recency."""
from datetime import datetime, timezone
from urllib.parse import urlsplit

# 0..1. Extend freely; unknown domains get DEFAULT.
DOMAIN_SCORES: dict[str, float] = {
    # Fact-checkers
    "factcheck.pib.gov.in": 0.97, "pib.gov.in": 0.9, "altnews.in": 0.92, "boomlive.in": 0.92,
    "factly.in": 0.92, "vishvasnews.com": 0.88, "newschecker.in": 0.88, "thequint.com": 0.78,
    "snopes.com": 0.9, "factcheck.org": 0.92, "politifact.com": 0.9, "fullfact.org": 0.92,
    "afp.com": 0.9, "factcheck.afp.com": 0.92,
    # Wire services / major outlets
    "reuters.com": 0.93, "apnews.com": 0.93, "bbc.com": 0.88, "bbc.co.uk": 0.88,
    "thehindu.com": 0.85, "indianexpress.com": 0.82, "hindustantimes.com": 0.78,
    "timesofindia.indiatimes.com": 0.74, "ndtv.com": 0.76, "livemint.com": 0.8,
    # Primary / institutional
    "who.int": 0.95, "rbi.org.in": 0.95, "eci.gov.in": 0.95, "mohfw.gov.in": 0.93,
    "isro.gov.in": 0.95, "nature.com": 0.95, "sciencedirect.com": 0.88,
    # Low-signal
    "wikipedia.org": 0.6, "reddit.com": 0.25, "x.com": 0.25, "twitter.com": 0.25,
    "facebook.com": 0.2, "youtube.com": 0.3, "quora.com": 0.2,
}
DEFAULT = 0.4


def domain_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def domain_score(url: str) -> float:
    host = domain_of(url)
    best = None
    for dom, score in DOMAIN_SCORES.items():
        if host == dom or host.endswith("." + dom):
            if best is None or len(dom) > len(best[0]):
                best = (dom, score)
    if best:
        return best[1]
    if host.endswith(".gov.in") or host.endswith(".gov") or host.endswith(".nic.in"):
        return 0.85
    if host.endswith(".edu") or host.endswith(".ac.in"):
        return 0.8
    return DEFAULT


def recency_factor(published: str | None) -> float:
    """1.0 for recent items, decaying to 0.85 for items older than ~3 years. Unknown date = 0.95."""
    if not published:
        return 0.95
    try:
        dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        years = (datetime.now(timezone.utc) - dt).days / 365
        return max(0.85, 1.0 - 0.05 * max(0.0, years))
    except ValueError:
        return 0.95


def score(url: str, published: str | None = None) -> float:
    return round(domain_score(url) * recency_factor(published), 3)
