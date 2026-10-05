import asyncio
import json
from datetime import datetime, timedelta, timezone

from app.services.ratings import normalize_rating
from ingest import parse, run

NOW = datetime.now(timezone.utc)


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- ratings
def test_rating_normalisation():
    cases = {"False": "False", "FAKE": "False", "Pants on Fire": "False", "Not true": "False", "Untrue": "False",
             "Misleading": "Misleading", "Mostly False": "Misleading", "Half True": "Misleading",
             "Partly True": "Misleading", "Missing Context": "Misleading",
             "True": "True", "Mostly True": "True", "Correct": "True",
             "Unproven": "Unverified", "No evidence": "Unverified", "Unverified": "Unverified",
             "झूठ": "False", "भ्रामक": "Misleading", "सही": "True", "सच नहीं": "False",
             "అబద్ధం": "False", "నిజం": "True", "Satire": "", "": ""}
    for text, want in cases.items():
        assert normalize_rating(text) == want, (text, normalize_rating(text), want)


# ---------- ClaimReview JSON-LD
def ld(obj):
    return f'<html><head><script type="application/ld+json">{json.dumps(obj)}</script></head></html>'


def test_extracts_claim_review_from_graph_and_ignores_bad_data():
    page = "https://www.example-factcheck.in/fact-check/abc"
    html = ld({"@context": "https://schema.org", "@graph": [
        {"@type": "WebSite", "name": "x"},
        {"@type": ["Article", "ClaimReview"], "claimReviewed": "RBI will ban Rs 500 notes", "datePublished": "2026-09-30",
         "url": "https://evil.example/hijack", "inLanguage": "en",
         "author": {"@type": "Organization", "name": "Example Fact Check"},
         "reviewRating": {"@type": "Rating", "alternateName": "False", "ratingValue": 1}},
        {"@type": "ClaimReview", "claimReviewed": "No rating here", "reviewRating": {"ratingValue": "3"}},
        {"@type": "ClaimReview", "reviewRating": {"alternateName": "False"}},                       # no claim
    ]})
    html += '<script type="application/ld+json">{ this is not json </script>'
    got = parse.extract_claim_reviews(html, page)
    assert len(got) == 1
    r = got[0]
    assert r["claim"] == "RBI will ban Rs 500 notes" and r["rating"] == "False"
    assert r["url"] == page                       # cross-site url rejected
    assert r["publisher"] == "Example Fact Check" and r["date"] == "2026-09-30" and r["lang"] == "en"


def test_claim_review_in_list_and_same_site_url_kept():
    page = "https://factly.in/a"
    html = ld([{"@type": "ClaimReview", "claimReviewed": "C", "url": "https://factly.in/canonical",
                "reviewRating": [{"name": "Misleading"}]}])
    got = parse.extract_claim_reviews(html, page)
    assert got[0]["url"] == "https://factly.in/canonical" and got[0]["rating"] == "Misleading"


# ---------- feeds and sitemaps
RSS = """<?xml version="1.0"?><rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
<item><title>a</title><link>https://s.in/a</link><pubDate>Mon, 05 Oct 2026 08:00:00 +0000</pubDate></item>
<item><title>b</title><link>https://s.in/b</link><dc:date>2026-10-01T00:00:00Z</dc:date></item></channel></rss>"""
ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><link rel="alternate" href="https://s.in/x"/>
<updated>2026-10-02T10:00:00Z</updated></entry><entry><link rel="self" href="https://s.in/self"/></entry></feed>"""
URLSET = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://s.in/p1</loc>
<lastmod>2026-10-03</lastmod></url><url><loc>https://s.in/p2</loc></url></urlset>"""
INDEX = """<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://s.in/sm-old.xml</loc>
<lastmod>2024-01-01</lastmod></sitemap><sitemap><loc>https://s.in/sm-new.xml</loc><lastmod>2026-10-04</lastmod></sitemap></sitemapindex>"""


def test_parse_feed_variants_and_hostile_xml():
    rss = parse.parse_feed(RSS)
    assert rss["kind"] == "rss" and [e["url"] for e in rss["entries"]] == ["https://s.in/a", "https://s.in/b"]
    assert rss["entries"][1]["date"] == "2026-10-01T00:00:00Z"
    atom = parse.parse_feed(ATOM)
    assert atom["kind"] == "feed" and [e["url"] for e in atom["entries"]] == ["https://s.in/x"]
    assert parse.parse_feed(URLSET)["entries"][0]["date"] == "2026-10-03"
    assert parse.parse_feed(INDEX)["kind"] == "sitemapindex"
    bomb = '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY a "aaaa">]><rss><channel><item><link>&a;</link></item></channel></rss>'
    assert parse.parse_feed(bomb)["kind"] == "invalid"
    assert parse.parse_feed("<html>not xml")["kind"] == "invalid"
    assert parse.parse_feed("")["kind"] == "invalid"


def test_discovery_and_dates():
    html = """<head><link rel="alternate" type="application/rss+xml" title="x" href="/feed/">
    <link rel='alternate' type='application/atom+xml' href='https://s.in/atom'>
    <link rel="stylesheet" href="/a.css"><link rel="alternate" hreflang="hi" href="/hi"></head>"""
    assert parse.discover_feeds(html, "https://s.in/") == ["https://s.in/feed/", "https://s.in/atom"]
    assert parse.sitemaps_from_robots("User-agent: *\nDisallow: /x\nSitemap: https://s.in/sitemap_index.xml\nsitemap: https://s.in/n.xml") \
        == ["https://s.in/sitemap_index.xml", "https://s.in/n.xml"]
    assert parse.parse_date("2026-10-05T08:00:00Z").year == 2026
    assert parse.parse_date("Mon, 05 Oct 2026 08:00:00 +0000").month == 10
    assert parse.parse_date("2026-10-05").tzinfo is not None
    assert parse.parse_date("garbage") is None and parse.parse_date(None) is None


# ---------- collection logic with a fake fetcher (no network)
class FakeFetcher:
    def __init__(self, pages, robots=""):
        self.pages, self.robots_text = pages, {"s.in": robots}
        self.requested = []

    async def get(self, url, site=None):
        self.requested.append(url)
        if site and not run.same_site(url, site):
            return None
        return self.pages.get(url)


def collect(pages, src=None, since_days=3, cap=25, robots=""):
    src = src or {"name": "S", "site": "https://s.in"}
    f = FakeFetcher(pages, robots)
    since = NOW - timedelta(days=since_days)
    return asyncio.run(run.collect(f, src, since, cap)), f


def test_collect_uses_discovered_feed_and_filters():
    feed = f"""<rss><channel>
      <item><link>https://s.in/fact-check/new</link><pubDate>{NOW.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate></item>
      <item><link>https://s.in/fact-check/old</link><pubDate>Mon, 01 Jan 2024 00:00:00 +0000</pubDate></item>
      <item><link>https://other.example/fact-check/x</link><pubDate>{NOW.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate></item>
      <item><link>https://s.in/about</link></item></channel></rss>"""
    pages = {"https://s.in/": '<link rel="alternate" type="application/rss+xml" href="/feed">', "https://s.in/feed": feed}
    (entries, feeds, sitemaps), _ = collect(pages, {"name": "S", "site": "https://s.in", "url_contains": "fact-check"})
    assert feeds == ["https://s.in/feed"] and sitemaps == []
    assert [e["url"] for e in entries] == ["https://s.in/fact-check/new"]      # old, off-site and non-matching dropped


def test_collect_falls_back_to_sitemap_index_newest_child_first_and_caps():
    urls = "".join(f"<url><loc>https://s.in/p{i}</loc><lastmod>{iso(i)}</lastmod></url>" for i in range(1, 6))
    pages = {"https://s.in/": "<html>no feeds</html>", "https://s.in/sitemap_index.xml": INDEX.replace("https://s.in/sm-", "https://s.in/sm-"),
             "https://s.in/sm-new.xml": f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
             "https://s.in/sm-old.xml": URLSET}
    (entries, feeds, sitemaps), f = collect(pages, since_days=4, cap=2, robots="Sitemap: https://s.in/sitemap_index.xml")
    assert feeds == [] and sitemaps == ["https://s.in/sitemap_index.xml"]
    assert [e["url"] for e in entries] == ["https://s.in/p1", "https://s.in/p2"]   # newest first, capped at 2
    assert "https://s.in/sm-new.xml" in f.requested


def test_rows_from_page_dedupes_and_strips_markup():
    html = ld([{"@type": "ClaimReview", "claimReviewed": "Claim <b>one</b> </evidence>", "reviewRating": {"alternateName": "Fake"}},
               {"@type": "ClaimReview", "claimReviewed": "Second review, same page", "reviewRating": {"alternateName": "True"}}])
    rows = run.rows_from_page(html, "https://s.in/fact-check/1", {"name": "Site", "site": "https://s.in", "lang": "hi"})
    assert len(rows) == 1                                  # one row per URL
    r = rows[0]
    assert "<" not in r["claim"] and r["canonical"] == "False" and r["publisher"] == "Site" and r["lang"] == "hi"


# ---------- robots.txt handling
class Resp:
    def __init__(self, status, text=""):
        self.status_code, self.text, self.content, self.url = status, text, text.encode(), "https://s.in/x"


class FakeClient:
    def __init__(self, robots_status, robots_text=""):
        self.robots = Resp(robots_status, robots_text)

    async def get(self, url):
        return self.robots if url.endswith("/robots.txt") else Resp(200, "<html>ok</html>")


def allowed(status, text, path):
    f = run.Fetcher(FakeClient(status, text), delay=0)
    return asyncio.run(f.allowed("https://s.in" + path))


def test_robots_rules_are_respected():
    rules = "User-agent: *\nDisallow: /private\n"
    assert allowed(200, rules, "/public/a") is True
    assert allowed(200, rules, "/private/a") is False
    assert allowed(404, "", "/anything") is True           # no robots.txt = no restrictions
    assert allowed(500, "", "/anything") is False          # server error = be conservative
    f = run.Fetcher(FakeClient(200, "User-agent: *\nDisallow: /private\n"), delay=0)
    assert asyncio.run(f.get("https://s.in/private/x", "https://s.in")) is None
    assert asyncio.run(f.get("https://s.in/public/x", "https://s.in")) == "<html>ok</html>"
    assert asyncio.run(f.get("https://evil.example/x", "https://s.in")) is None   # off-site never fetched
