"""Evidence retrieval: local fact-check store (Postgres FTS) + Google Fact Check API + web search."""
import asyncio
import logging
import re
from contextvars import ContextVar

import httpx
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.db import SessionLocal
from app.models import FactCheck
from app.services import credibility
from app.services.ratings import normalize_rating
from app.services.sanitize import attr, clean

log = logging.getLogger("fnv.evidence")
GOOGLE_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
TAVILY_URL = "https://api.tavily.com/search"
# \w alone drops Devanagari/Telugu vowel signs, which splits words; include those blocks explicitly.
TOKEN_RE = re.compile(r"[\w\u0900-\u0D7F]+", re.UNICODE)

# Evaluation only: domains whose results are dropped so a benchmark claim cannot retrieve its own answer.
EXCLUDE_DOMAINS: ContextVar[tuple[str, ...]] = ContextVar("exclude_domains", default=())


def _item(source_type: str, title: str, url: str, snippet: str, publisher: str = "",
          rating: str = "", published: str | None = None, claim_text: str = "") -> dict:
    return {
        "claim_text": clean(claim_text, 400),
        "source_type": source_type, "title": clean(title, 300), "url": url, "snippet": clean(snippet, 700),
        "publisher": attr(publisher or credibility.domain_of(url)), "rating": attr(rating),
        "canonical": normalize_rating(rating),
        "published": published, "credibility": credibility.score(url, published),
    }


async def local_search(claim: str) -> list[dict]:
    words = list(dict.fromkeys(w.lower() for w in TOKEN_RE.findall(claim.replace("_", " ")) if len(w) > 2))[:12]
    if not words:
        return []
    q = " | ".join(words)  # OR query: long claims rarely match every word
    sql = text(
        "SELECT claim, rating, publisher, url, reviewed_at FROM fact_checks "
        "WHERE to_tsvector('simple', claim) @@ to_tsquery('simple', :q) "
        "ORDER BY ts_rank(to_tsvector('simple', claim), to_tsquery('simple', :q)) DESC LIMIT 5"
    )
    try:
        async with SessionLocal() as s:
            rows = (await s.execute(sql, {"q": q})).all()
    except Exception as exc:  # noqa: BLE001
        log.warning("local search failed: %s", exc)
        return []
    return [_item("fact_check_db", r.claim, r.url, f"Rated: {r.rating}. {r.claim}", r.publisher, r.rating,
                  r.reviewed_at or None) for r in rows]


async def google_factcheck(claim: str) -> list[dict]:
    key = get_settings().google_factcheck_api_key
    if not key:
        return []
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get(GOOGLE_URL, params={"query": claim[:300], "key": key, "pageSize": 5})
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        log.warning("google factcheck failed: %s", exc)
        return []
    items: list[dict] = []
    for cl in data.get("claims", []):
        for rev in cl.get("claimReview", []):
            if not rev.get("url"):
                continue
            items.append(_item("fact_check_api", rev.get("title") or cl.get("text", ""), rev["url"],
                               f"Claim: {cl.get('text', '')} | Rated: {rev.get('textualRating', '')}",
                               rev.get("publisher", {}).get("name", ""), rev.get("textualRating", ""),
                               rev.get("reviewDate"), claim_text=cl.get("text", "")))
    await _remember(items, claim)
    return items


async def web_search(claim: str) -> list[dict]:
    key = get_settings().tavily_api_key
    if not key:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(TAVILY_URL, headers={"Authorization": f"Bearer {key}"},
                             json={"query": claim[:300], "max_results": 6, "search_depth": "basic",
                                   "topic": "general"})
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        log.warning("web search failed: %s", exc)
        return []
    return [_item("web", x.get("title", ""), x["url"], x.get("content", ""),
                  published=x.get("published_date")) for x in data.get("results", []) if x.get("url")]


async def _remember(items: list[dict], claim: str) -> None:
    """Grow the local RAG corpus with every ClaimReview we fetch."""
    if not items:
        return
    try:
        async with SessionLocal() as s:
            for it in items:
                stmt = insert(FactCheck).values(
                    claim=it.get("claim_text") or it["title"] or claim, rating=it["rating"][:200],
                    canonical=it["canonical"], publisher=it["publisher"][:200], url=it["url"],
                    reviewed_at=(it["published"] or "")[:40])
                await s.execute(stmt.on_conflict_do_update(index_elements=["url"], set_={
                    "rating": stmt.excluded.rating, "canonical": stmt.excluded.canonical,
                    "reviewed_at": stmt.excluded.reviewed_at}))
            await s.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("could not store fact-checks: %s", exc)


async def gather_evidence(claim: str, limit: int = 6) -> list[dict]:
    results = await asyncio.gather(local_search(claim), google_factcheck(claim), web_search(claim))
    seen: dict[str, dict] = {}
    blocked = EXCLUDE_DOMAINS.get()
    for group in results:
        for it in group:
            host = credibility.domain_of(it["url"])
            if any(host == d or host.endswith("." + d) for d in blocked):
                continue
            seen.setdefault(it["url"], it)
    ranked = sorted(seen.values(), key=lambda x: x["credibility"], reverse=True)
    return ranked[:limit]
