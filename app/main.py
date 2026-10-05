import asyncio
import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.routes import router
from app.config import get_settings
from app.db import init_db

logging.basicConfig(level=logging.INFO)
mimetypes.add_type("application/manifest+json", ".webmanifest")
STATIC_DIR = Path(__file__).parent / "static"


async def _retry_init() -> None:
    for delay in (5, 15, 30, 60, 120, 300):
        await asyncio.sleep(delay)
        if await init_db():
            return


@asynccontextmanager
async def lifespan(_: FastAPI):
    retry = None
    if not await init_db():          # never blocks startup; /api/health reports the DB state
        retry = asyncio.create_task(_retry_init())
    yield
    if retry:
        retry.cancel()


app = FastAPI(
    title="Fake News Verifier",
    version="0.3.0",
    description="Evidence-based claim checking. Results are assessments, not absolute truth.",
    lifespan=lifespan,
)
origins = [o.strip() for o in get_settings().allowed_origins.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api")
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])


@app.get("/share", include_in_schema=False)
async def share_target(title: str = "", text: str = "", url: str = ""):
    """PWA share target: the Android share sheet opens the app with the shared text prefilled."""
    shared = text.strip()
    if url and url not in shared:
        shared = f"{shared}\n{url}".strip()
    return RedirectResponse("/#!/?" + urlencode({"shared": shared[:5000]}), status_code=303)


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")  # AngularJS app; keep last
