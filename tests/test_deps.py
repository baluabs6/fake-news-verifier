from starlette.requests import Request

from app.api import deps


def req(xff: str | None, client="9.9.9.9"):
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "headers": headers, "client": (client, 1234), "scheme": "https",
                    "server": ("x", 443), "path": "/", "query_string": b""})


def test_client_ip_ignores_spoofed_first_entry():
    assert deps.client_ip(req("6.6.6.6, 1.2.3.4")) == "1.2.3.4"   # last = appended by our proxy
    assert deps.client_ip(req(None)) == "9.9.9.9"
