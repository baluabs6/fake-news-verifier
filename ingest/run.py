"""Daily ingestion of published fact-checks into the fact_checks table.

  python -m ingest.run --check-sources            # show what feeds/sitemaps each site resolves to (no DB, no page fetches)
  python -m ingest.run --dry-run --since-days 3   # fetch and parse, print rows, write nothing
  python -m ingest.run --since-days 3             # fetch, parse, upsert into DATABASE_URL

Politeness: obeys robots.txt, identifies itself (set INGEST_USER_AGENT to include your contact URL), waits between
requests to the same host, fetches only same-site URLs, and stores just the claim, rating, publisher, date and link.
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import robotparser
from urllib.parse import urlsplit

from app.services.ratings import normalize_rating
from app.services.sanitize import clean
from ingest import parse

log = logging.getLogger("fnv.ingest")
UA = os.getenv("INGEST_USER_AGENT", "FakeNewsVerifierBot/0.3 (research project; set INGEST_USER_AGENT with a contact URL)")
MAX_BYTES = 5_000_000
OLDEST = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _bare(host: str) -> str:
    host = (host or "").lower()
    return host[4:] if host.startswith("www.") else host


def same_site(url: str, site: str) -> bool:
    h, s = _bare(urlsplit(url).hostname), _bare(urlsplit(site).hostname)
    return bool(h) and (h == s or h.endswith("." + s))


class Fetcher:
    """Polite HTTP: robots.txt aware, rate limited per host, same-site only, size capped."""

    def __init__(self, client, delay: float = 1.0):
        self.client, self.delay = client, delay
        self.robots: dict[str, robotparser.RobotFileParser] = {}
        self.robots_text: dict[str, str] = {}
        self._last: dict[str, float] = {}

    async def _load_robots(self, scheme: str, host: str) -> None:
        rp = robotparser.RobotFileParser()
        text = ""
        try:
            r = await self.client.get(f"{scheme}://{host}/robots.txt")
            if r.status_code == 200:
                text = r.text
                rp.parse(text.splitlines())
                rp.modified()                      # without this, can_fetch() always answers False
            elif 400 <= r.status_code < 500:
                rp.allow_all = True                # RFC 9309: no robots file means no restrictions
            else:
                rp.disallow_all = True             # server error: be conservative
        except Exception:                          # noqa: BLE001
            rp.disallow_all = True
        self.robots[host], self.robots_text[host] = rp, text

    async def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        if parts.netloc not in self.robots:
            await self._load_robots(parts.scheme, parts.netloc)
        return self.robots[parts.netloc].can_fetch(UA, url)

    async def get(self, url: str, site: str | None = None) -> str | None:
        if site and not same_site(url, site):
            return None
        if not await self.allowed(url):
            log.info("robots.txt disallows %s", url)
            return None
        host = urlsplit(url).netloc
        wait = self.delay - (time.monotonic() - self._last.get(host, 0))
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            r = await self.client.get(url)
            self._last[host] = time.monotonic()
            if r.status_code != 200 or len(r.content) > MAX_BYTES:
                return None
            if site and not same_site(str(r.url), site):    # redirected off-site
                return None
            return r.text
        except Exception as exc:                            # noqa: BLE001
            log.warning("fetch failed %s: %s", url, exc.__class__.__name__)
            return None


async def resolve(f, src: dict) -> tuple[list[str], list[str]]:
    """Find feeds (preferred) or sitemaps for a source: explicit config, then <link rel=alternate>, then robots.txt."""
    site = src["site"].rstrip("/")
    feeds, sitemaps = list(src.get("feeds", [])), list(src.get("sitemaps", []))
    if feeds or sitemaps:
        return feeds, sitemaps
    home = await f.get(site + "/", site)
    if home:
        feeds = parse.discover_feeds(home, site + "/")
    if not feeds:
        sitemaps = parse.sitemaps_from_robots(f.robots_text.get(urlsplit(site).netloc, ""))
        if not sitemaps:
            sitemaps = [site + "/sitemap.xml"]
    return feeds, sitemaps


async def collect(f, src: dict, since: datetime, cap: int) -> tuple[list[dict], list[str], list[str]]:
    site = src["site"].rstrip("/")
    feeds, sitemaps = await resolve(f, src)
    entries: list[dict] = []
    for u in feeds:
        txt = await f.get(u, site)
        if txt:
            entries += parse.parse_feed(txt)["entries"]

    async def walk(url: str, depth: int) -> None:
        txt = await f.get(url, site)
        if not txt:
            return
        pf = parse.parse_feed(txt)
        if pf["kind"] == "sitemapindex" and depth < 2:
            kids = sorted(pf["entries"], key=lambda e: parse.parse_date(e["date"]) or OLDEST, reverse=True)[:3]
            for k in kids:
                await walk(k["url"], depth + 1)
        elif pf["entries"] and pf["kind"] != "sitemapindex":
            entries.extend(pf["entries"])

    if not entries:
        for sm in sitemaps:
            await walk(sm, 0)

    hint = src.get("url_contains")
    seen: dict[str, dict] = {}
    for e in entries:
        if not same_site(e["url"], site) or (hint and hint not in e["url"]):
            continue
        dt = parse.parse_date(e["date"])
        if dt and dt < since:
            continue
        seen.setdefault(e["url"], {"url": e["url"], "dt": dt})
    ordered = sorted(seen.values(), key=lambda e: e["dt"] or OLDEST, reverse=True)[:cap]
    return ordered, feeds, sitemaps


def rows_from_page(html: str, url: str, src: dict) -> list[dict]:
    rows: dict[str, dict] = {}
    for r in parse.extract_claim_reviews(html, url):
        claim = clean(r["claim"], 600)
        if not claim or r["url"] in rows:        # one row per URL (the table is unique on url)
            continue
        rows[r["url"]] = {"claim": claim, "rating": clean(r["rating"], 200), "canonical": normalize_rating(r["rating"]),
                          "publisher": clean(r["publisher"] or src["name"], 200), "url": r["url"],
                          "reviewed_at": r["date"][:40], "lang": (r["lang"] or src.get("lang", ""))[:10]}
    return list(rows.values())


async def known_urls(urls: list[str]) -> set[str]:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import FactCheck
    if not urls:
        return set()
    async with SessionLocal() as s:
        return set((await s.execute(select(FactCheck.url).where(FactCheck.url.in_(urls)))).scalars().all())


async def upsert(rows: list[dict]) -> None:
    from sqlalchemy.dialects.postgresql import insert

    from app.db import SessionLocal
    from app.models import FactCheck
    if not rows:
        return
    stmt = insert(FactCheck).values(rows)
    stmt = stmt.on_conflict_do_update(index_elements=["url"], set_={c: getattr(stmt.excluded, c) for c in
                                      ("claim", "rating", "canonical", "publisher", "reviewed_at", "lang")})
    async with SessionLocal() as s:
        await s.execute(stmt)
        await s.commit()


async def run_source(f, src: dict, args, dry: bool) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=args.since_days)
    entries, feeds, sitemaps = await collect(f, src, since, args.max_per_source)
    stat = {"name": src["name"], "feeds": len(feeds), "sitemaps": len(sitemaps), "candidates": len(entries),
            "fetched": 0, "found": 0, "stored": 0}
    if args.check_sources:
        stat["feed_urls"], stat["sitemap_urls"] = feeds, sitemaps
        return stat
    urls = [e["url"] for e in entries]
    skip = set() if (args.refresh or dry) else await known_urls(urls)
    batch: list[dict] = []
    for u in urls:
        if u in skip:
            continue
        html = await f.get(u, src["site"])
        if html is None:
            continue
        stat["fetched"] += 1
        rows = rows_from_page(html, u, src)
        stat["found"] += len(rows)
        batch += rows
    if dry:
        for r in batch:
            print(json.dumps(r, ensure_ascii=False))
    else:
        await upsert(batch)
    stat["stored"] = 0 if dry else len(batch)
    return stat


async def main() -> int:
    import httpx

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", default=str(Path(__file__).with_name("sources.json")))
    ap.add_argument("--since-days", type=int, default=3)
    ap.add_argument("--max-per-source", type=int, default=25)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests to the same host")
    ap.add_argument("--refresh", action="store_true", help="re-fetch URLs that are already stored (picks up revised ratings)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check-sources", action="store_true")
    ap.add_argument("--only", help="run just the source with this name")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    sources = json.loads(Path(args.sources).read_text(encoding="utf-8"))
    if args.only:
        sources = [s for s in sources if s["name"].lower() == args.only.lower()]
    dry = args.dry_run or args.check_sources
    if not dry:
        from app.db import init_db
        if not await init_db():
            print("Database unavailable: check DATABASE_URL.", file=sys.stderr)
            return 1

    stats = []
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": UA}) as client:
        f = Fetcher(client, args.delay)
        for src in sources:
            try:
                stats.append(await run_source(f, src, args, dry))
            except Exception as exc:  # noqa: BLE001  (one broken site must not stop the others)
                log.exception("source failed: %s", src["name"])
                stats.append({"name": src["name"], "error": exc.__class__.__name__})

    print(f"\n{'source':<16}{'feeds':>6}{'maps':>6}{'cands':>7}{'fetched':>9}{'found':>7}{'stored':>8}")
    for s in stats:
        if "error" in s:
            print(f"{s['name']:<16}ERROR {s['error']}")
            continue
        print(f"{s['name']:<16}{s['feeds']:>6}{s['sitemaps']:>6}{s['candidates']:>7}{s['fetched']:>9}{s['found']:>7}{s['stored']:>8}")
        for u in s.get("feed_urls", []) + s.get("sitemap_urls", []):
            print(f"    -> {u}")
    reachable = [s for s in stats if "error" not in s and (s["feeds"] or s["sitemaps"] or s["candidates"])]
    return 0 if reachable else 2   # exit non-zero when nothing at all could be resolved, so CI shows a red run


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
