"""Smoke tests — the service boots and answers its probe."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health-check/")
    assert response.status_code == 200
    assert response.json() == {"status": "OK"}


def test_no_trailing_slash_redirect() -> None:
    """`redirect_slashes=False` must hold from the first commit.

    With redirects on, `/v1/contracts/` would 307 into the list endpoint and
    the Validator — which does not follow redirects, and which calls
    `.get("status")` on whatever it receives — would either fail the read or
    raise AttributeError outside its fail-closed path. Asserting it here means
    the property cannot regress once real routes land.
    """
    client = TestClient(app)
    response = client.get("/health-check", follow_redirects=False)
    assert response.status_code == 404
