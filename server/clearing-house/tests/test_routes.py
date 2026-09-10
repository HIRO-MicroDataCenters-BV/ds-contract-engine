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

import base64
from typing import Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from app.core.models import STATUS_ACTIVE, AuditEvent, Contract
from app.core.repository import (
    EVENT_REGISTERED,
    EVENT_STATUS_CHANGED,
    ContractPosition,
    ContractQuery,
    Repositories,
)
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
        # The real repository writes this in the same commit as the contract,
        # so the fake must too — otherwise history tests pass here and fail
        # against SQLite, which is the one thing a fake must never do.
        await self.append_event(
            AuditEvent(
                event_type=EVENT_REGISTERED,
                jti=contract.jti,
                order_id=contract.order_id,
                consumer_id=contract.consumer_id,
                to_status=contract.status,
                occurred_at=contract.registered_at,
                detail=f"status={contract.status} exp={contract.exp}",
            )
        )
        return contract

    async def get(self, jti: str) -> Optional[Contract]:
        return self.contracts.get(jti)

    async def set_status(
        self, jti: str, status: str, changed_at: int
    ) -> Optional[Contract]:
        contract = self.contracts.get(jti)
        if contract is None:
            return None
        previous = contract.status
        contract.status = status
        contract.status_changed_at = changed_at
        await self.append_event(
            AuditEvent(
                event_type=EVENT_STATUS_CHANGED,
                jti=jti,
                order_id=contract.order_id,
                consumer_id=contract.consumer_id,
                from_status=previous,
                to_status=status,
                occurred_at=changed_at,
                detail=f"{previous} -> {status}",
            )
        )
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

    async def list_contracts(
        self,
        query: ContractQuery,
        limit: int,
        after: Optional[ContractPosition] = None,
    ) -> List[Contract]:
        rows = list(self.contracts.values())
        if query.status is not None:
            rows = [c for c in rows if c.status == query.status]
        if query.consumer_id is not None:
            rows = [c for c in rows if c.consumer_id == query.consumer_id]
        if query.order_id is not None:
            rows = [c for c in rows if c.order_id == query.order_id]
        if query.exp_at_or_before is not None:
            rows = [c for c in rows if c.exp <= query.exp_at_or_before]
        if query.exp_after is not None:
            rows = [c for c in rows if c.exp > query.exp_after]

        # Same total order as SqlRepository: (registered_at, jti), descending.
        # Python compares tuples lexicographically, which is exactly the SQL
        # OR/AND expansion — so this is a faithful model, not an approximation.
        rows.sort(key=lambda c: (c.registered_at, c.jti), reverse=True)
        if after is not None:
            rows = [c for c in rows if (c.registered_at, c.jti) < after]
        return rows[:limit]

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


# --- GET /v1/contracts/{jti}/history ------------------------------------


def test_history_returns_an_object_not_an_array(client) -> None:
    """Load-bearing, not stylistic.

    The Validator's adapter calls body.get("status") on whatever a contracts
    URL returns. On an object that yields None and it denies gracefully; on a
    list it raises AttributeError and escapes its fail-closed path as a 500.
    """
    client.post("/v1/contracts", json=register_body())
    body = client.get("/v1/contracts/abc-111/history").json()
    assert isinstance(body, dict)
    assert isinstance(body["items"], list)


def test_history_of_a_new_contract_has_the_registration(client) -> None:
    client.post("/v1/contracts", json=register_body())
    items = client.get("/v1/contracts/abc-111/history").json()["items"]
    assert len(items) == 1
    assert items[0]["event_type"] == "contract.registered"
    assert items[0]["from_status"] is None
    assert items[0]["to_status"] == "active"


def test_history_records_a_status_change_with_both_ends(client) -> None:
    client.post("/v1/contracts", json=register_body())
    client.patch("/v1/contracts/abc-111/status", json={"status": "revoked"})
    items = client.get("/v1/contracts/abc-111/history").json()["items"]
    assert [e["event_type"] for e in items] == [
        "contract.registered",
        "contract.status_changed",
    ]
    assert (items[1]["from_status"], items[1]["to_status"]) == ("active", "revoked")


def test_history_includes_refused_attempts(client) -> None:
    """The reason an operator opens this endpoint at all."""
    client.post("/v1/contracts", json=register_body())
    client.patch("/v1/contracts/abc-111/status", json={"status": "revoked"})
    client.patch("/v1/contracts/abc-111/status", json={"status": "active"})

    items = client.get("/v1/contracts/abc-111/history").json()["items"]
    refused = [e for e in items if e["event_type"] == "contract.status_change_rejected"]
    assert len(refused) == 1
    assert (refused[0]["from_status"], refused[0]["to_status"]) == ("revoked", "active")


def test_history_is_oldest_first(client) -> None:
    """Timeline order, and by seq — two events can share a timestamp."""
    client.post("/v1/contracts", json=register_body())
    client.patch("/v1/contracts/abc-111/status", json={"status": "completed"})
    client.patch("/v1/contracts/abc-111/status", json={"status": "active"})

    seqs = [
        e["seq"] for e in client.get("/v1/contracts/abc-111/history").json()["items"]
    ]
    assert seqs == sorted(seqs)


def test_history_of_an_unknown_contract_is_404(client) -> None:
    """Not an empty list: registration always writes an event, so empty would
    mean a bug. Matches GET /v1/contracts/{jti}."""
    r = client.get("/v1/contracts/never-registered/history")
    assert r.status_code == 404
    assert "not registered" in r.json()["detail"]


def test_history_does_not_leak_another_contracts_events(client) -> None:
    client.post("/v1/contracts", json=register_body("abc-111"))
    client.post("/v1/contracts", json=register_body("xyz-222"))
    client.patch("/v1/contracts/xyz-222/status", json={"status": "revoked"})

    items = client.get("/v1/contracts/abc-111/history").json()["items"]
    assert {e["jti"] for e in items} == {"abc-111"}


# --- GET /v1/contracts ---------------------------------------------------


def seed(repository, jti: str, registered_at: int, **fields) -> None:
    """Put a contract straight into the fake, bypassing the frozen clock, so
    ordering tests can control registered_at."""
    repository.contracts[jti] = Contract(
        jti=jti,
        order_id=fields.get("order_id", "ord-1"),
        consumer_id=fields.get("consumer_id", "dr-rahul"),
        status=fields.get("status", "active"),
        iat=1_699_999_000,
        exp=fields.get("exp", 1_700_003_600),
        registered_at=registered_at,
        status_changed_at=registered_at,
    )


def jtis(response) -> List[str]:
    return [c["jti"] for c in response.json()["items"]]


def walk(client, **params) -> List[List[str]]:
    """Follow next_cursor to the end. Returns each page's jtis."""
    pages, cursor = [], None
    while True:
        query = dict(params, **({"cursor": cursor} if cursor else {}))
        body = client.get("/v1/contracts", params=query).json()
        pages.append([c["jti"] for c in body["items"]])
        cursor = body["next_cursor"]
        if cursor is None:
            return pages


def test_list_returns_an_object_not_an_array(client) -> None:
    """Same reason as history: the Validator calls body.get() on what a
    contracts URL returns, and a list would make it raise."""
    body = client.get("/v1/contracts").json()
    assert isinstance(body, dict)
    assert body == {"items": [], "next_cursor": None}


def test_list_is_newest_first(client, repository) -> None:
    seed(repository, "old", 100)
    seed(repository, "new", 300)
    seed(repository, "mid", 200)
    assert jtis(client.get("/v1/contracts")) == ["new", "mid", "old"]


def test_list_breaks_ties_by_jti(client) -> None:
    """The Generator mints several contracts per second. Without a tiebreaker
    those have no defined order, and a page boundary between them could show
    one twice or never."""
    for jti in ("b", "c", "a"):
        client.post("/v1/contracts", json=register_body(jti))
    assert jtis(client.get("/v1/contracts")) == ["c", "b", "a"]


def test_paging_visits_every_contract_exactly_once(client, repository) -> None:
    """Including across ties — the case most likely to break."""
    for jti, at in [
        ("a", 100),
        ("b", 100),
        ("c", 100),
        ("d", 200),
        ("e", 200),
        ("f", 300),
        ("g", 300),
    ]:
        seed(repository, jti, at)

    pages = walk(client, limit=3)
    assert [len(p) for p in pages] == [3, 3, 1]
    flat = [j for p in pages for j in p]
    assert flat == ["g", "f", "e", "d", "c", "b", "a"]


def test_the_last_page_has_no_cursor(client, repository) -> None:
    seed(repository, "a", 100)
    seed(repository, "b", 200)
    assert (
        client.get("/v1/contracts", params={"limit": 2}).json()["next_cursor"] is None
    )
    assert (
        client.get("/v1/contracts", params={"limit": 1}).json()["next_cursor"]
        is not None
    )


def test_new_arrivals_do_not_shift_the_next_page(client, repository) -> None:
    """Why this is cursor-paged. With offset=3, both arrivals push every row
    down, and page two would repeat the end of page one."""
    for i in range(6):
        seed(repository, f"c{i}", 100 + i)

    first = client.get("/v1/contracts", params={"limit": 3}).json()
    assert jtis_of(first) == ["c5", "c4", "c3"]

    seed(repository, "late-1", 900)
    seed(repository, "late-2", 901)

    second = client.get(
        "/v1/contracts", params={"limit": 3, "cursor": first["next_cursor"]}
    )
    assert jtis(second) == ["c2", "c1", "c0"]


def jtis_of(body: dict) -> List[str]:
    return [c["jti"] for c in body["items"]]


def test_list_filters_by_status(client, repository) -> None:
    seed(repository, "a", 100, status="active")
    seed(repository, "r", 200, status="revoked")
    assert jtis(client.get("/v1/contracts", params={"status": "revoked"})) == ["r"]


def test_list_filters_by_consumer_and_order(client, repository) -> None:
    seed(repository, "x", 100, consumer_id="alice", order_id="o-1")
    seed(repository, "y", 200, consumer_id="alice", order_id="o-2")
    seed(repository, "z", 300, consumer_id="bob", order_id="o-1")
    assert jtis(client.get("/v1/contracts", params={"consumer_id": "alice"})) == [
        "y",
        "x",
    ]
    assert jtis(
        client.get("/v1/contracts", params={"consumer_id": "alice", "order_id": "o-1"})
    ) == ["x"]


def test_expired_includes_the_boundary_second(client, repository) -> None:
    """RFC 7519: a token must not be accepted on or after exp. So a contract
    whose exp is exactly now is expired, not about to be."""
    seed(repository, "past", 100, exp=FROZEN_NOW - 1)
    seed(repository, "boundary", 200, exp=FROZEN_NOW)
    seed(repository, "future", 300, exp=FROZEN_NOW + 1)
    assert jtis(client.get("/v1/contracts", params={"expired": "true"})) == [
        "boundary",
        "past",
    ]
    assert jtis(client.get("/v1/contracts", params={"expired": "false"})) == ["future"]


def test_expired_is_independent_of_status(client, repository) -> None:
    """The case an admin screen most needs to get right: status says active,
    but the permit is already dead."""
    seed(repository, "zombie", 100, status="active", exp=FROZEN_NOW - 60)
    seed(repository, "live", 200, status="active", exp=FROZEN_NOW + 60)
    assert jtis(
        client.get("/v1/contracts", params={"status": "active", "expired": "true"})
    ) == ["zombie"]


def b64(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


@pytest.mark.parametrize(
    "cursor",
    [
        "!!!not-a-cursor!!!",
        b64("not json"),
        b64('{"r": 1, "j": "x"}'),  # an object, not a pair
        b64("[1]"),  # wrong length
        b64('[true, "x"]'),  # bool is an int in Python — must not pass
        b64('["1", "x"]'),  # position as a string
        b64('[1, ""]'),  # empty jti
    ],
)
def test_a_damaged_cursor_is_400_not_500(client, cursor) -> None:
    r = client.get("/v1/contracts", params={"cursor": cursor})
    assert r.status_code == 400


@pytest.mark.parametrize("limit", [0, 201])
def test_limit_is_bounded(client, limit) -> None:
    assert client.get("/v1/contracts", params={"limit": limit}).status_code == 422


def test_list_rejects_an_unknown_status(client) -> None:
    assert client.get("/v1/contracts", params={"status": "deleted"}).status_code == 422
