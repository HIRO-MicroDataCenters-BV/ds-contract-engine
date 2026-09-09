"""The HTTP contract.

These status codes are not ours to choose: the Contract Generator and
Validator are already written against the stub this service replaces, and
their client code was read to derive every assertion here.

The 404 case matters most. The Validator's adapter does:

    if resp.status_code == 404:
        return "not_registered"        # a graceful deny

so an unknown jti returning 500, or 200 with an odd status, breaks its
fail-closed path rather than merely returning the wrong thing.

Runs against a fake repository — no database, no migrations, no Docker.
"""

from typing import Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from app.core.models import STATUS_ACTIVE, AuditEvent, Contract
from app.core.repository import Repositories
from app.core.usecases import ContractUsecases
from app.main import app
from app.rest_api.routes.contracts import get_usecase

FROZEN_NOW = 1_700_000_000


class FakeRepository(Repositories):
    """In-memory stand-in.

    Subclassing Repositories is deliberate: Python refuses to instantiate it
    if a method is missing, so this fake cannot silently drift out of step
    with the interface the real implementation satisfies.
    """

    def __init__(self, database: object = None) -> None:
        self.contracts: Dict[str, Contract] = {}
        self.events: List[AuditEvent] = []
        self._seq = 0

    async def register(self, contract: Contract) -> Contract:
        existing = self.contracts.get(contract.jti)
        if existing is not None:
            return existing
        self.contracts[contract.jti] = contract
        return contract

    async def get(self, jti: str) -> Optional[Contract]:
        return self.contracts.get(jti)

    async def set_status(
        self, jti: str, status: str, changed_at: int
    ) -> Optional[Contract]:
        contract = self.contracts.get(jti)
        if contract is None:
            return None
        contract.status = status
        contract.status_changed_at = changed_at
        return contract

    async def append_event(self, event: AuditEvent) -> AuditEvent:
        self._seq += 1
        event.seq = self._seq
        self.events.append(event)
        return event

    async def events_for_jti(self, jti: str) -> List[AuditEvent]:
        return [e for e in self.events if e.jti == jti]

    async def events_for_order(self, order_id: str) -> List[AuditEvent]:
        return [e for e in self.events if e.order_id == order_id]

    async def health_check(self) -> bool:
        return True


@pytest.fixture
def repository() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def client(repository: FakeRepository):
    app.dependency_overrides[get_usecase] = lambda: ContractUsecases(
        repository, clock=lambda: FROZEN_NOW
    )
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def register_body(jti: str = "abc-111", **overrides) -> dict:
    body = {
        "jti": jti,
        "order_id": "ord-1",
        "status": "active",
        "consumer_id": "dr-rahul",
        "iat": 1_699_999_000,
        "exp": 1_700_003_600,
    }
    body.update(overrides)
    return body


# --- POST /v1/contracts -------------------------------------------------


def test_register_returns_201(client) -> None:
    r = client.post("/v1/contracts", json=register_body())
    assert r.status_code == 201


def test_register_response_is_an_object_with_the_expected_fields(client) -> None:
    body = client.post("/v1/contracts", json=register_body()).json()
    assert isinstance(body, dict)
    for field in ("jti", "order_id", "status", "consumer_id", "iat", "exp"):
        assert field in body, f"the stub returned {field}; callers may rely on it"


def test_register_stamps_its_own_time_not_the_callers(client) -> None:
    body = client.post("/v1/contracts", json=register_body()).json()
    assert body["registered_at"] == FROZEN_NOW
    assert body["iat"] == 1_699_999_000  # the caller's value, untouched


def test_register_is_idempotent(client) -> None:
    """The Generator makes one attempt with no retry budget, and the stub this
    replaces upserts. A duplicate must not become an error."""
    first = client.post("/v1/contracts", json=register_body())
    second = client.post("/v1/contracts", json=register_body())
    assert first.status_code == second.status_code == 201
    assert second.json()["registered_at"] == first.json()["registered_at"]


def test_register_rejects_a_non_active_status(client) -> None:
    """Only `active` is accepted at registration — a contract arriving already
    revoked would be meaningless."""
    r = client.post("/v1/contracts", json=register_body(status="revoked"))
    assert r.status_code == 422


def test_register_rejects_an_empty_jti(client) -> None:
    r = client.post("/v1/contracts", json=register_body(jti=""))
    assert r.status_code == 422


# --- GET /v1/contracts/{jti} --------------------------------------------


def test_get_returns_200_and_the_status(client) -> None:
    client.post("/v1/contracts", json=register_body())
    r = client.get("/v1/contracts/abc-111")
    assert r.status_code == 200
    assert r.json()["status"] == STATUS_ACTIVE


def test_get_unknown_returns_404(client) -> None:
    """The single most load-bearing assertion in this file. The Validator maps
    404 to "not_registered" and denies gracefully; a 500 makes it raise,
    escaping its fail-closed path entirely."""
    assert client.get("/v1/contracts/never-seen").status_code == 404


def test_get_always_returns_a_json_object(client) -> None:
    """The Validator calls body.get("status") on whatever comes back. A JSON
    array would raise AttributeError outside its fail-closed path."""
    client.post("/v1/contracts", json=register_body())
    body = client.get("/v1/contracts/abc-111").json()
    assert isinstance(body, dict)
    assert isinstance(body["status"], str)


def test_no_trailing_slash_redirect(client) -> None:
    """redirect_slashes=False. httpx does not follow redirects and treats any
    3xx as failure, so a 307 here would break the Validator outright."""
    r = client.get("/v1/contracts/", follow_redirects=False)
    assert r.status_code != 307
    assert r.status_code == 404


# --- PATCH /v1/contracts/{jti}/status -----------------------------------


def test_revoke_returns_200(client) -> None:
    """Exactly 200 — asserted by examples/compose-e2e-test.sh."""
    client.post("/v1/contracts", json=register_body())
    r = client.patch("/v1/contracts/abc-111/status", json={"status": "revoked"})
    assert r.status_code == 200
    assert r.json()["status"] == "revoked"


def test_revoke_is_visible_to_the_very_next_read(client) -> None:
    """Read-your-writes. The Validator reads status on every data access, so a
    revocation that is not immediately visible is a revocation that did not
    happen."""
    client.post("/v1/contracts", json=register_body())
    client.patch("/v1/contracts/abc-111/status", json={"status": "revoked"})
    assert client.get("/v1/contracts/abc-111").json()["status"] == "revoked"


def test_reactivating_a_revoked_contract_returns_409(client) -> None:
    client.post("/v1/contracts", json=register_body())
    client.patch("/v1/contracts/abc-111/status", json={"status": "revoked"})
    r = client.patch("/v1/contracts/abc-111/status", json={"status": "active"})
    assert r.status_code == 409
    assert "revoked" in r.json()["detail"]


def test_a_refused_change_leaves_the_status_alone(client) -> None:
    client.post("/v1/contracts", json=register_body())
    client.patch("/v1/contracts/abc-111/status", json={"status": "revoked"})
    client.patch("/v1/contracts/abc-111/status", json={"status": "active"})
    assert client.get("/v1/contracts/abc-111").json()["status"] == "revoked"


def test_a_refused_change_is_recorded(client, repository) -> None:
    """A log of successes only would hide that someone tried."""
    client.post("/v1/contracts", json=register_body())
    client.patch("/v1/contracts/abc-111/status", json={"status": "revoked"})
    client.patch("/v1/contracts/abc-111/status", json={"status": "active"})
    assert any(
        e.event_type == "contract.status_change_rejected" for e in repository.events
    )


def test_patch_unknown_returns_404(client) -> None:
    r = client.patch("/v1/contracts/never-seen/status", json={"status": "revoked"})
    assert r.status_code == 404


def test_patch_rejects_an_unknown_status(client) -> None:
    client.post("/v1/contracts", json=register_body())
    r = client.patch("/v1/contracts/abc-111/status", json={"status": "deleted"})
    assert r.status_code == 422


# --- health -------------------------------------------------------------


def test_health_check(client) -> None:
    r = client.get("/health-check/")
    assert r.status_code == 200
    assert r.json() == {"status": "OK"}
