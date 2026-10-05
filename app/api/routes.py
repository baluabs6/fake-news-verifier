import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import origin, rate_limit
from app.config import get_settings
from app.db import db_ok, get_session
from app.models import Check, Flag, Review
from app.schemas import CheckRequest, FlagRequest
from app.services import cards, privacy, scam
from app.services.ingest import IngestError, fetch_article
from app.services.llm import LLMNotConfigured
from app.services.verify import run_pipeline

log = logging.getLogger("fnv.api")
router = APIRouter()
_slots: asyncio.Semaphore | None = None


@router.get("/health")
async def health():
    s = get_settings()
    return {
        "status": "ok",
        "database": await db_ok(),
        "anthropic_configured": bool(s.anthropic_api_key),
        "google_factcheck_configured": bool(s.google_factcheck_api_key),
        "web_search_configured": bool(s.tavily_api_key),
        "admin_enabled": bool(s.admin_key),
    }


async def _process(session: AsyncSession, *, content: str, input_type: str, shown: str,
                   client_id: str, save: bool) -> dict:
    global _slots
    if _slots is None:
        _slots = asyncio.Semaphore(get_settings().max_concurrent_checks)
    content, redacted = privacy.redact(content)
    if input_type != "url":      # a URL must stay intact or it can no longer be fetched or re-checked
        shown, _ = privacy.redact(shown)
    try:
        async with _slots:
            result = await asyncio.wait_for(run_pipeline(content, input_type), timeout=100)
    except asyncio.TimeoutError as exc:
        raise HTTPException(504, "The check took too long. Please try again.") from exc
    except LLMNotConfigured as exc:
        raise HTTPException(503, "The verifier is not configured yet (missing ANTHROPIC_API_KEY).") from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("pipeline failed")
        raise HTTPException(502, "The verification pipeline failed. Please try again.") from exc

    result["warnings"] = scam.signals(shown if input_type == "url" else content)
    if redacted:
        result["privacy"] = {"redacted": redacted}
    check_id = uuid.uuid4().hex[:12]
    result.update(id=check_id, input_type=input_type, input=shown[:500], saved=False)

    if save:
        try:
            result["saved"] = True
            session.add(Check(id=check_id, client_id=client_id[:64], input_type=input_type, input_text=shown,
                              verdict=result["verdict"], confidence=result["confidence"], result=result))
            await session.commit()
        except Exception:  # noqa: BLE001  (still return the verdict if storage is down)
            log.exception("could not store check")
            await session.rollback()
            result["saved"] = False
    return result


@router.post("/check", dependencies=[Depends(rate_limit)])
async def create_check(body: CheckRequest, session: AsyncSession = Depends(get_session),
                       x_client_id: str = Header(default="")):
    s = get_settings()
    if body.url:
        try:
            content = await fetch_article(body.url)
        except IngestError as exc:
            raise HTTPException(422, str(exc)) from exc
        input_type, shown = "url", body.url
    else:
        if len(body.text) > s.max_input_chars:
            raise HTTPException(422, f"Text is too long (max {s.max_input_chars} characters).")
        content, input_type, shown = body.text, "text", body.text
    return await _process(session, content=content, input_type=input_type, shown=shown,
                          client_id=x_client_id, save=body.save)


def _is_stale(result: dict) -> bool:
    try:
        return datetime.now(timezone.utc) > datetime.fromisoformat(result["stale_after"])
    except (KeyError, ValueError, TypeError):
        return False


@router.get("/checks/{check_id}")
async def get_check(check_id: str, session: AsyncSession = Depends(get_session)):
    row = await session.get(Check, check_id)
    if not row:
        raise HTTPException(404, "Check not found.")
    result = dict(row.result)
    result["stale"] = _is_stale(result)
    review = await session.get(Review, check_id)
    if review:
        result["review"] = {"verdict": review.verdict, "note": review.note,
                            "reviewed_at": review.reviewed_at.isoformat()}
    return result


@router.post("/checks/{check_id}/recheck", dependencies=[Depends(rate_limit)])
async def recheck(check_id: str, session: AsyncSession = Depends(get_session),
                  x_client_id: str = Header(default="")):
    row = await session.get(Check, check_id)
    if not row:
        raise HTTPException(404, "Check not found.")
    if row.input_type == "url":
        try:
            content = await fetch_article(row.input_text)
        except IngestError as exc:
            raise HTTPException(422, str(exc)) from exc
    else:
        content = row.input_text
    return await _process(session, content=content, input_type=row.input_type, shown=row.input_text,
                          client_id=x_client_id, save=True)


@router.get("/checks/{check_id}/card")
async def share_card(check_id: str, request: Request, lang: str = "en",
                     session: AsyncSession = Depends(get_session)):
    row = await session.get(Check, check_id)
    if not row:
        raise HTTPException(404, "Check not found.")
    lang = lang if lang in cards.TEXT else "en"
    link = f"{origin(request)}/#!/result/{check_id}"
    return {"lang": lang, "text": cards.build_card(row.result, link, lang), "link": link}


@router.post("/checks/{check_id}/flag", dependencies=[Depends(rate_limit)])
async def flag_check(check_id: str, body: FlagRequest, session: AsyncSession = Depends(get_session)):
    if not await session.get(Check, check_id):
        raise HTTPException(404, "Check not found.")
    session.add(Flag(check_id=check_id, reason=body.reason, note=body.note.strip()))
    await session.commit()
    return {"ok": True}


@router.get("/checks")
async def history(limit: int = 20, session: AsyncSession = Depends(get_session),
                  x_client_id: str = Header(default="")):
    if not x_client_id:
        return []
    q = (select(Check).where(Check.client_id == x_client_id[:64])
         .order_by(Check.created_at.desc()).limit(min(limit, 50)))
    rows = (await session.execute(q)).scalars().all()
    return [{"id": r.id, "input": r.input_text[:140], "verdict": r.verdict, "confidence": r.confidence,
             "created_at": r.created_at.isoformat()} for r in rows]


@router.get("/trending")
async def trending(session: AsyncSession = Depends(get_session)):
    """Most-checked text claims this week. Only claims checked by 3+ different browsers are shown,
    so one person's private input is never exposed."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    distinct_clients = func.count(func.distinct(Check.client_id))
    q = (select(func.min(Check.input_text).label("text"), func.count().label("n"),
                func.max(Check.id).label("latest"))
         .where(Check.created_at >= cutoff, Check.input_type == "text", Check.client_id != "")
         .group_by(func.lower(func.left(Check.input_text, 200)))
         .having(distinct_clients >= 3).order_by(desc("n")).limit(10))
    out = []
    for r in (await session.execute(q)).all():
        latest = await session.get(Check, r.latest)
        out.append({"text": r.text[:200], "count": r.n, "id": r.latest,
                    "verdict": latest.verdict if latest else "Unverified"})
    return out
