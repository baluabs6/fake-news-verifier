"""Heuristic scam/phishing signals. These are warnings, never a verdict."""
import re
from urllib.parse import urlsplit

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "cutt.ly", "rb.gy", "is.gd", "goo.gl", "shorturl.at", "tiny.cc"}
RISKY_TLDS = (".xyz", ".top", ".click", ".icu", ".buzz", ".tk", ".ml", ".ga", ".cf", ".gq", ".work", ".live", ".cyou")
BRANDS = {  # brand token -> domains that are genuinely theirs
    "hdfc": ("hdfcbank.com",), "icici": ("icicibank.com",), "paytm": ("paytm.com",),
    "phonepe": ("phonepe.com",), "amazon": ("amazon.in", "amazon.com"), "flipkart": ("flipkart.com",),
    "irctc": ("irctc.co.in",), "uidai": ("uidai.gov.in",), "incometax": ("incometax.gov.in",),
    "epfo": ("epfindia.gov.in",), "sbi": ("sbi.co.in", "onlinesbi.sbi"),
}
PATTERNS = [
    (re.compile(r"\bkyc\b.{0,60}\b(expire|update|block|suspend|verify)", re.I | re.S), "Claims your KYC/account will be blocked unless you act"),
    (re.compile(r"\b(you have won|you['’]ve won|lucky draw|lottery|claim your (prize|reward|gift))\b", re.I), "Prize or lottery bait"),
    (re.compile(r"\bfree (recharge|gift|iphone|laptop|data)\b", re.I), "Offers something valuable for free"),
    (re.compile(r"\bforward (this )?(message )?to \d+", re.I), "Chain-message pressure to forward to many people"),
    (re.compile(r"\b(link|offer) (will )?expires? (today|soon|in)", re.I), "Artificial urgency"),
    (re.compile(r"(लॉटरी|इनाम जीत|केवाईसी)"), "Prize/KYC bait (Hindi)"),
    (re.compile(r"(లాటరీ|కేవైసీ|బహుమతి గెలు)"), "Prize/KYC bait (Telugu)"),
]


def _host_signals(url: str) -> list[str]:
    host = (urlsplit(url).hostname or "").lower()
    out = []
    if host in SHORTENERS:
        out.append(f"Shortened link ({host}) hides the real destination")
    if host.endswith(RISKY_TLDS):
        out.append(f"Link uses a domain ending often seen in scams ({host})")
    if host.startswith("xn--") or ".xn--" in host:
        out.append("Link uses look-alike (punycode) characters")
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        out.append("Link points to a raw IP address")
    for brand, official in BRANDS.items():
        if brand in host and not any(host == d or host.endswith("." + d) for d in official):
            out.append(f"Link mentions '{brand}' but is not an official {brand} domain")
    return out


def signals(text: str) -> list[str]:
    found: list[str] = []
    for url in URL_RE.findall(text or "")[:10]:
        found += _host_signals(url)
    for pat, msg in PATTERNS:
        if pat.search(text or ""):
            found.append(msg)
    return list(dict.fromkeys(found))[:6]
