"""Reviewer endpoints. All require the X-Admin-Key header to equal the ADMIN_KEY setting."""
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import Float, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import rate_limit_admin, require_admin
from app.db import get_session
from app.models import Check, Flag, Review
from app.schemas import ReviewRequest

router = APIRouter(dependencies=[Depends(rate_limit_admin), Depends(require_admin)])


@router.get("/queue")
async def queue(session: AsyncSession = Depends(get_session)):
    """Open user flags first, then low-confidence decided verdicts nobody has reviewed yet."""
    reviewed = set((await session.execute(select(Review.check_id))).scalars().all())
    items: dict[str, dict] = {}

    flags = (await session.execute(
        select(Flag).where(Flag.status == "open").order_by(Flag.created_at.desc()).limit(100))).scalars().all()
    for f in flags:
        chk = await session.get(Check, f.check_id)
        if not chk:
            continue
        it = items.setdefault(f.check_id, {"id": f.check_id, "input": chk.input_text[:300], "verdict": chk.verdict,
                                           "confidence": chk.confidence, "reasons": [], "notes": []})
        it["reasons"].append(f.reason)
        if f.note:
            it["notes"].append(f.note)

    low = (await session.execute(
        select(Check).where(Check.verdict.in_(["True", "False", "Misleading"]), Check.confidence < 0.5)
        .order_by(Check.created_at.desc()).limit(50))).scalars().all()
    for chk in low:
        if chk.id not in reviewed:
            it = items.setdefault(chk.id, {"id": chk.id, "input": chk.input_text[:300], "verdict": chk.verdict,
                                           "confidence": chk.confidence, "reasons": [], "notes": []})
            if not it["reasons"]:
                it["reasons"].append("low_confidence")
    return list(items.values())


@router.post("/review/{check_id}")
async def review(check_id: str, body: ReviewRequest, session: AsyncSession = Depends(get_session)):
    if not await session.get(Check, check_id):
        raise HTTPException(404, "Check not found.")
    await session.merge(Review(check_id=check_id, verdict=body.verdict, note=body.note.strip(),
                               reviewed_at=datetime.now(timezone.utc)))
    await session.execute(update(Flag).where(Flag.check_id == check_id).values(status="resolved"))
    await session.commit()
    return {"ok": True}


@router.get("/export", response_class=PlainTextResponse)
async def export(session: AsyncSession = Depends(get_session)):
    """Reviewed text claims as JSONL, ready for `python -m eval.run_eval --data ... --format jsonl`."""
    rows = (await session.execute(
        select(Check, Review).join(Review, Review.check_id == Check.id).where(Check.input_type == "text")
    )).all()
    lines = [json.dumps({"claim": c.input_text, "label": r.verdict, "lang": "und"}, ensure_ascii=False)
             for c, r in rows]
    return PlainTextResponse("\n".join(lines), media_type="application/x-ndjson")


@router.get("/stats")
async def stats(session: AsyncSession = Depends(get_session)):
    week = datetime.now(timezone.utc) - timedelta(days=7)
    total = (await session.execute(select(func.count()).select_from(Check))).scalar_one()
    last7 = (await session.execute(
        select(func.count()).select_from(Check).where(Check.created_at >= week))).scalar_one()
    by_verdict = dict((await session.execute(select(Check.verdict, func.count()).group_by(Check.verdict))).all())
    tok_in = Check.result["usage"]["input_tokens"].astext.cast(Float)
    tok_out = Check.result["usage"]["output_tokens"].astext.cast(Float)
    avg_in, avg_out = (await session.execute(select(func.avg(tok_in), func.avg(tok_out)))).one()
    open_flags = (await session.execute(
        select(func.count()).select_from(Flag).where(Flag.status == "open"))).scalar_one()
    reviewed = (await session.execute(select(func.count()).select_from(Review))).scalar_one()
    return {"total_checks": total, "last_7_days": last7, "by_verdict": by_verdict,
            "avg_input_tokens": round(avg_in or 0), "avg_output_tokens": round(avg_out or 0),
            "open_flags": open_flags, "reviewed": reviewed}
