"""app.main — / e /health."""

from fastapi.testclient import TestClient


def test_index_html(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


def test_health_degraded_empty(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "degraded"
    assert data["tracks"] == 0


def test_health_ok_populated(client_populated: TestClient):
    r = client_populated.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["tracks"] >= 1


def test_health_503_without_library(client: TestClient):
    client.app.state.library = None
    r = client.get("/health")
    assert r.status_code == 503
