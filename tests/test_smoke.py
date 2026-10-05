from fastapi.testclient import TestClient

from app.main import app
from app.services import credibility


def test_credibility_table():
    assert credibility.score("https://www.reuters.com/x") > credibility.score("https://random-blog.example/x")
    assert credibility.domain_score("https://factcheck.pib.gov.in/abc") > 0.9


def test_health_and_homepage():
    with TestClient(app) as client:  # DB may be down in CI; the app must still start
        assert client.get("/api/health").json()["status"] == "ok"
        assert "Fake News Verifier" in client.get("/").text


def test_check_requires_exactly_one_input():
    with TestClient(app) as client:
        assert client.post("/api/check", json={}).status_code == 422
        assert client.post("/api/check", json={"text": "a", "url": "https://x.com"}).status_code == 422


def test_admin_disabled_without_key_and_manifest_served():
    with TestClient(app) as client:
        assert client.get("/api/admin/stats").status_code in (401, 503)
        m = client.get("/manifest.webmanifest")
        assert m.status_code == 200 and "share_target" in m.json()
        r = client.get("/share?text=hello", follow_redirects=False)
        assert r.status_code == 303 and "shared=hello" in r.headers["location"]
