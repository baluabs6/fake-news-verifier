import logging
from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

log = logging.getLogger("fnv.db")


class Base(DeclarativeBase):
    pass


def _normalize(url: str) -> tuple[str, bool]:
    """Turn any common Postgres URL into an asyncpg URL; asyncpg wants ssl as a connect arg."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    sslmode = query.pop("sslmode", "")
    query.pop("channel_binding", None)
    ssl = sslmode in {"require", "verify-ca", "verify-full"}
    return urlunsplit(parts._replace(query=urlencode(query))), ssl


_url, _ssl = _normalize(get_settings().database_url)
_connect_args: dict = {"ssl": True} if _ssl else {}
if "-pooler" in _url or ":6543" in _url:  # pgbouncer (Neon pooled, Supabase pooler): no prepared statements
    _connect_args["statement_cache_size"] = 0
engine = create_async_engine(_url, pool_pre_ping=True, pool_size=5, max_overflow=5, connect_args=_connect_args)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> bool:
    """Create tables + full-text index. Never crashes startup; /api/health reports the state."""
    from app import models  # noqa: F401  (register tables)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            for col, ddl in (("canonical", "VARCHAR(20)"), ("lang", "VARCHAR(10)")):   # additive migration for v0.2 databases
                await conn.execute(text(f"ALTER TABLE fact_checks ADD COLUMN IF NOT EXISTS {col} {ddl} NOT NULL DEFAULT ''"))
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_fact_checks_fts "
                    "ON fact_checks USING GIN (to_tsvector('simple', claim))"
                )
            )
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("Database init failed: %s", exc)
        return False


async def db_ok() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False
