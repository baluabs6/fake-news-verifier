from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FactCheck(Base):
    """Previously published fact-checks (ClaimReview data): the local RAG corpus."""

    __tablename__ = "fact_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim: Mapped[str] = mapped_column(Text)
    rating: Mapped[str] = mapped_column(String(200), default="")
    publisher: Mapped[str] = mapped_column(String(200), default="")
    url: Mapped[str] = mapped_column(Text, unique=True)
    reviewed_at: Mapped[str] = mapped_column(String(40), default="")
    canonical: Mapped[str] = mapped_column(String(20), default="")   # True/False/Misleading/Unverified or ""
    lang: Mapped[str] = mapped_column(String(10), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Check(Base):
    """One user submission and its full result (shareable by id)."""

    __tablename__ = "checks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    input_type: Mapped[str] = mapped_column(String(10))
    input_text: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    result: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Flag(Base):
    """A user reporting a verdict as wrong or missing context."""

    __tablename__ = "flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Review(Base):
    """A human reviewer's verdict for a check (also becomes labelled eval data)."""

    __tablename__ = "reviews"

    check_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    verdict: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
