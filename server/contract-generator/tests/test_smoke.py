"""Smoke tests — make sure the app boots and the contract pipeline works
end-to-end against the in-memory stubs.
"""

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


def test_generate_contract_for_local_item():
    """A request whose items belong to this node should mint successfully."""
    client = TestClient(app)
    body = {
        "consumer_id": "researcher-test",
        "order_id": "00000000-0000-0000-0000-000000000001",
        "ttl_seconds": 3600,
        "items": [
            {
                "id": "https://localhost/dataset-smoke-1",
                "identifier": "dataset_smoke_1",
                "title": "Smoke test dataset",
                "hash": "sha256:" + "a" * 64,
            }
        ],
    }
    resp = client.post("/v1/contracts", json=body)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert "token" in out
    assert "jti" in out
    assert "exp" in out


def test_generate_contract_rejects_wrong_node():
    """Items belonging to another node must be refused."""
    client = TestClient(app)
    body = {
        "consumer_id": "researcher-test",
        "order_id": "00000000-0000-0000-0000-000000000002",
        "items": [
            {
                "id": "https://some-other-node.example.org/dataset-x",
                "identifier": "dataset_x",
                "title": "Cross-node dataset",
                "hash": "sha256:" + "b" * 64,
            }
        ],
    }
    resp = client.post("/v1/contracts", json=body)
    assert resp.status_code == 400
    assert "does not match" in resp.text or "node" in resp.text.lower()
