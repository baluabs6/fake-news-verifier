"""Turn a URL into article text, safely (SSRF guard + trafilatura)."""
import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx
import trafilatura


class IngestError(ValueError):
    pass


async def _assert_public(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise IngestError("Only http(s) URLs are supported.")
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, parts.hostname, None)
    except socket.gaierror as exc:
        raise IngestError("Could not resolve that URL.") from exc
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
        except ValueError as exc:
            raise IngestError("That address is not allowed.") from exc
        if not ip.is_global or ip.is_multicast:  # blocks private, loopback, link-local, CGNAT, reserved
            raise IngestError("That address is not allowed.")


async def fetch_article(url: str, max_chars: int = 8000) -> str:
    await _assert_public(url)
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False,
                                     headers={"User-Agent": "FakeNewsVerifier/0.1"}) as client:
            resp = await client.get(url)
            hops = 0
            while resp.is_redirect and hops < 3:  # re-validate every redirect target
                nxt = str(resp.next_request.url) if resp.next_request else ""
                await _assert_public(nxt)
                resp = await client.get(nxt)
                hops += 1
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise IngestError(f"Could not fetch the page: {exc.__class__.__name__}") from exc
    if len(resp.content) > 3_000_000:
        raise IngestError("That page is too large to analyse.")
    text = await asyncio.to_thread(trafilatura.extract, resp.text) or ""
    if len(text.strip()) < 40:
        raise IngestError("No readable article text found at that URL.")
    return text[:max_chars]
