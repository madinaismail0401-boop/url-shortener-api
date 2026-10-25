import importlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app as app_module


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "DB_PATH", str(tmp_path / "test_links.db"))
    return TestClient(app_module.app)


def test_create_link_returns_code_and_url(client):
    response = client.post("/links", json={"long_url": "https://example.com/page"})
    assert response.status_code == 201
    data = response.json()
    assert data["code"]
    assert data["long_url"] == "https://example.com/page"
    assert data["short_url"] == f"/{data['code']}"


def test_custom_alias_redirects_and_counts_clicks(client):
    created = client.post("/links", json={
        "long_url": "https://example.com/page",
        "alias": "my-page"
    })
    assert created.status_code == 201

    redirected = client.get("/my-page", follow_redirects=False)
    assert redirected.status_code == 307
    assert redirected.headers["location"] == "https://example.com/page"

    stats = client.get("/links/my-page/stats")
    assert stats.status_code == 200
    assert stats.json()["total_clicks"] == 1
    assert stats.json()["last_clicked_at"] is not None


def test_duplicate_alias_returns_helpful_conflict(client):
    payload = {"long_url": "https://example.com", "alias": "same-code"}
    assert client.post("/links", json=payload).status_code == 201
    response = client.post("/links", json=payload)
    assert response.status_code == 409
    assert "already in use" in response.json()["detail"]


def test_invalid_url_is_rejected(client):
    response = client.post("/links", json={"long_url": "not-a-url"})
    assert response.status_code == 400


def test_invalid_alias_is_rejected(client):
    response = client.post("/links", json={
        "long_url": "https://example.com",
        "alias": "x"
    })
    assert response.status_code == 400


def test_unknown_code_returns_404(client):
    response = client.get("/unknown-code", follow_redirects=False)
    assert response.status_code == 404


def test_expired_link_returns_410(client):
    expiry = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    # API rejects past expiries at creation, so insert an expired row to test redirect behaviour.
    conn = app_module.get_connection()
    conn.execute(
        "INSERT INTO links (code, long_url, created_at, expires_at) VALUES (?, ?, ?, ?)",
        ("old-link", "https://example.com", datetime.now(timezone.utc).isoformat(), expiry),
    )
    conn.commit()
    conn.close()

    response = client.get("/old-link", follow_redirects=False)
    assert response.status_code == 410
    assert "expired" in response.json()["detail"].lower()


def test_stats_for_unknown_code_returns_404(client):
    response = client.get("/links/no-such-code/stats")
    assert response.status_code == 404
