"""Smoke tests — make sure the stub boots and basic registration works."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_ok():
    client = TestClient(app)
    response = client.get("/health-check/")
    assert response.status_code == 200
    assert response.json() == {"status": "OK"}


def test_register_and_read_contract():
    client = TestClient(app)
    body = {
        "jti": "test-jti-001",
        "order_id": "test-order-001",
        "status": "active",
        "consumer_id": "test-consumer",
        "iat": 1745409600,
        "exp": 1745413200,
    }
    resp = client.post("/v1/contracts", json=body)
    assert resp.status_code == 201

    read = client.get("/v1/contracts/test-jti-001")
    assert read.status_code == 200
    assert read.json()["status"] == "active"
