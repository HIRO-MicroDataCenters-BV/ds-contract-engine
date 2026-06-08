"""Smoke tests — make sure the app boots and health-check responds."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_ok():
    client = TestClient(app)
    response = client.get("/health-check/")
    assert response.status_code == 200
    assert response.json() == {"status": "OK"}
