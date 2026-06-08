"""Smoke tests — make sure the app boots and health-check responds."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_ok():
    client = TestClient(app)
    response = client.get("/health-check/")
    assert response.status_code == 200
    assert response.json() == {"status": "OK"}


def test_jwks_endpoint_serves_a_key():
    client = TestClient(app)
    response = client.get("/.well-known/jwks.json")
    assert response.status_code == 200
    body = response.json()
    assert "keys" in body
    assert len(body["keys"]) >= 1
    assert body["keys"][0]["alg"] == "EdDSA"
    assert body["keys"][0]["kty"] == "OKP"
