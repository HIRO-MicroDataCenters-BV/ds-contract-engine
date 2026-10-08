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
from app.core.repository import (
    EVENT_REGISTERED,
    EVENT_STATUS_CHANGED,
    ContractQuery,
    ContractSort,
    EventQuery,
    Repositories,
)
from app.core.usecases import ContractUsecases
from app.main import app
from app.rest_api.routes import ledger
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
        self,
        jti: str,
        status: str,
        changed_at: int,
        actor: Optional[str] = None,
        reason: Optional[str] = None,
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
                actor=actor,
                reason=reason,
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

    # Filtering is kept apart from ordering and slicing, exactly as
    # SqlRepository builds one WHERE clause for both list and count — so the
    # fake's totals cannot disagree with its rows either.

    def _matching_contracts(self, query: ContractQuery) -> List[Contract]:
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
        return rows

    async def list_contracts(
        self,
        query: ContractQuery,
        limit: int,
        offset: int = 0,
        sort: ContractSort = ContractSort(),
    ) -> List[Contract]:
        rows = self._matching_contracts(query)
        # Same total order as SqlRepository: (column, jti), both in the
        # sort's direction.
        rows.sort(
            key=lambda c: (getattr(c, sort.column), c.jti), reverse=sort.descending
        )
        return rows[offset : offset + limit]

    async def count_contracts(self, query: ContractQuery) -> int:
        return len(self._matching_contracts(query))

    def _matching_events(self, query: EventQuery) -> List[AuditEvent]:
        rows = list(self.events)
        for field in (
            "event_type",
            "jti",
            "order_id",
            "consumer_id",
            "actor",
            "from_status",
            "to_status",
        ):
            wanted = getattr(query, field)
            if wanted is not None:
                rows = [e for e in rows if getattr(e, field) == wanted]
        if query.occurred_at_or_after is not None:
            rows = [e for e in rows if e.occurred_at >= query.occurred_at_or_after]
        if query.occurred_before is not None:
            rows = [e for e in rows if e.occurred_at < query.occurred_before]
        return rows

    async def list_events(
        self, query: EventQuery, limit: int, offset: int = 0
    ) -> List[AuditEvent]:
        rows = self._matching_events(query)
        rows.sort(key=lambda e: e.seq, reverse=True)
        return rows[offset : offset + limit]

    async def count_events(self, query: EventQuery) -> int:
        return len(self._matching_events(query))

    async def health_check(self) -> bool:
        return True


@pytest.fixture
def repository() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def client(repository: FakeRepository):
    def usecases() -> ContractUsecases:
        return ContractUsecases(repository, clock=lambda: FROZEN_NOW)

    # Each route module defines its own get_usecase, so each must be
    # overridden — miss one and its routes quietly reach for a real database.
    app.dependency_overrides[get_usecase] = usecases
    app.dependency_overrides[ledger.get_usecase] = usecases
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


# --- paging, shared by both list endpoints -----------------------------


def walk(client, path: str, **params) -> List[dict]:
    """Fetch page 1, then every further page total_pages says exists."""
    first = client.get(path, params=dict(params, page=1)).json()
    pages = [first]
    for n in range(2, first["total_pages"] + 1):
        pages.append(client.get(path, params=dict(params, page=n)).json())
    return pages


def every_item(pages: List[dict]) -> List[dict]:
    return [item for page in pages for item in page["items"]]


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


def contracts(client, **params):
    return client.get("/v1/contracts", params=params)


def test_list_returns_an_object_not_an_array(client) -> None:
    """The Validator calls body.get() on what a contracts URL returns, and a
    list would make it raise."""
    assert contracts(client).json() == {
        "items": [],
        "page": 1,
        "limit": 50,
        "total": 0,
        "total_pages": 0,
    }


def test_list_is_newest_first(client, repository) -> None:
    seed(repository, "old", 100)
    seed(repository, "new", 300)
    seed(repository, "mid", 200)
    assert jtis(contracts(client)) == ["new", "mid", "old"]


def test_list_breaks_ties_by_jti(client) -> None:
    """The Generator mints several contracts per second. Without a tiebreaker
    those have no defined order, and offset paging could then show one twice
    or never — even with nothing new arriving."""
    for jti in ("b", "c", "a"):
        client.post("/v1/contracts", json=register_body(jti))
    assert jtis(contracts(client)) == ["c", "b", "a"]


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

    pages = walk(client, "/v1/contracts", limit=3)
    assert [len(p["items"]) for p in pages] == [3, 3, 1]
    assert [c["jti"] for c in every_item(pages)] == ["g", "f", "e", "d", "c", "b", "a"]


def test_list_sorts_by_registered_oldest_first(client, repository) -> None:
    seed(repository, "old", 100)
    seed(repository, "new", 300)
    seed(repository, "mid", 200)
    assert jtis(contracts(client, sort="registered_at", direction="asc")) == [
        "old",
        "mid",
        "new",
    ]


def test_list_sorts_by_expiry_in_either_direction(client, repository) -> None:
    """Expiry order is independent of registration order — the seeds are
    registered in the opposite order to the one they expire in."""
    seed(repository, "late", 100, exp=FROZEN_NOW + 300)
    seed(repository, "soon", 200, exp=FROZEN_NOW + 100)
    seed(repository, "gone", 300, exp=FROZEN_NOW - 100)
    assert jtis(contracts(client, sort="exp", direction="asc")) == [
        "gone",
        "soon",
        "late",
    ]
    assert jtis(contracts(client, sort="exp", direction="desc")) == [
        "late",
        "soon",
        "gone",
    ]


def test_sort_direction_defaults_to_descending(client, repository) -> None:
    seed(repository, "soon", 100, exp=FROZEN_NOW + 100)
    seed(repository, "late", 200, exp=FROZEN_NOW + 300)
    assert jtis(contracts(client, sort="exp")) == ["late", "soon"]


def test_ascending_is_exactly_descending_reversed(client, repository) -> None:
    """jti breaks ties in the sort's own direction. Were it always
    descending, contracts sharing an expiry would keep their relative order
    when the column flips, and the list would not simply turn over."""
    for jti, exp in [("a", 500), ("b", 500), ("c", 400), ("d", 500), ("e", 400)]:
        seed(repository, jti, 100, exp=exp)
    descending = jtis(contracts(client, sort="exp", direction="desc"))
    ascending = jtis(contracts(client, sort="exp", direction="asc"))
    assert descending == ["d", "b", "a", "e", "c"]
    assert ascending == list(reversed(descending))


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_sorted_paging_visits_every_contract_exactly_once(
    client, repository, direction
) -> None:
    """The paging guarantee holds for every sort, ties included."""
    for jti, exp in [
        ("a", 500),
        ("b", 500),
        ("c", 400),
        ("d", 400),
        ("e", 400),
        ("f", 300),
        ("g", 500),
    ]:
        seed(repository, jti, 100, exp=exp)

    pages = walk(client, "/v1/contracts", limit=3, sort="exp", direction=direction)
    seen = [c["jti"] for c in every_item(pages)]
    assert sorted(seen) == ["a", "b", "c", "d", "e", "f", "g"]
    assert seen == jtis(contracts(client, limit=50, sort="exp", direction=direction))


@pytest.mark.parametrize(
    "params",
    [
        {"sort": "jti"},
        {"sort": "status_changed_at"},
        {"sort": ""},
        {"direction": "up"},
        {"direction": "DESC"},
    ],
)
def test_list_rejects_an_unknown_sort(client, params) -> None:
    """Refused rather than quietly ignored: an admin who asked for a sort
    must not be shown the default order as if it were the one they chose."""
    assert contracts(client, **params).status_code == 422


def test_a_page_reports_where_it_is(client, repository) -> None:
    for i in range(7):
        seed(repository, f"c{i}", 100 + i)
    body = contracts(client, page=2, limit=3).json()
    assert {k: body[k] for k in ("page", "limit", "total", "total_pages")} == {
        "page": 2,
        "limit": 3,
        "total": 7,
        "total_pages": 3,
    }
    assert [c["jti"] for c in body["items"]] == ["c3", "c2", "c1"]


def test_a_page_past_the_end_is_empty_not_an_error(client, repository) -> None:
    """The totals still say how far the list really goes."""
    for i in range(7):
        seed(repository, f"c{i}", 100 + i)
    r = contracts(client, page=99, limit=3)
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert (r.json()["total"], r.json()["total_pages"]) == (7, 3)


def test_the_total_agrees_with_the_rows_the_filters_return(client, repository) -> None:
    """Count and list are separate queries. If they ever applied different
    filters, "showing 51-100 of N" would quietly lie."""
    seed(repository, "a", 100, status="revoked", consumer_id="alice")
    seed(repository, "b", 200, status="active", consumer_id="alice")
    seed(repository, "c", 300, status="revoked", consumer_id="bob")
    seed(repository, "d", 400, status="revoked", consumer_id="alice")
    seed(
        repository, "e", 500, status="revoked", consumer_id="alice", exp=FROZEN_NOW - 1
    )

    for params in (
        {},
        {"status": "revoked"},
        {"consumer_id": "alice"},
        {"status": "revoked", "consumer_id": "alice"},
        {"status": "revoked", "consumer_id": "alice", "expired": "false"},
    ):
        pages = walk(client, "/v1/contracts", limit=2, **params)
        assert pages[0]["total"] == len(every_item(pages)), params


def test_list_filters_by_status(client, repository) -> None:
    seed(repository, "a", 100, status="active")
    seed(repository, "r", 200, status="revoked")
    body = contracts(client, status="revoked").json()
    assert [c["jti"] for c in body["items"]] == ["r"]
    assert body["total"] == 1


def test_list_filters_by_consumer_and_order(client, repository) -> None:
    seed(repository, "x", 100, consumer_id="alice", order_id="o-1")
    seed(repository, "y", 200, consumer_id="alice", order_id="o-2")
    seed(repository, "z", 300, consumer_id="bob", order_id="o-1")
    assert jtis(contracts(client, consumer_id="alice")) == ["y", "x"]
    assert jtis(contracts(client, consumer_id="alice", order_id="o-1")) == ["x"]


def test_expired_includes_the_boundary_second(client, repository) -> None:
    """RFC 7519: a token must not be accepted on or after exp. So a contract
    whose exp is exactly now is expired, not about to be."""
    seed(repository, "past", 100, exp=FROZEN_NOW - 1)
    seed(repository, "boundary", 200, exp=FROZEN_NOW)
    seed(repository, "future", 300, exp=FROZEN_NOW + 1)
    assert jtis(contracts(client, expired="true")) == ["boundary", "past"]
    assert jtis(contracts(client, expired="false")) == ["future"]


def test_expired_is_independent_of_status(client, repository) -> None:
    """The case an admin screen most needs to get right: status says active,
    but the permit is already dead."""
    seed(repository, "zombie", 100, status="active", exp=FROZEN_NOW - 60)
    seed(repository, "live", 200, status="active", exp=FROZEN_NOW + 60)
    assert jtis(contracts(client, status="active", expired="true")) == ["zombie"]


@pytest.mark.parametrize("page", [0, -1, "two"])
def test_page_must_be_a_positive_number(client, page) -> None:
    """Pages count from 1."""
    assert contracts(client, page=page).status_code == 422


@pytest.mark.parametrize("limit", [0, 201])
def test_limit_is_bounded(client, limit) -> None:
    assert contracts(client, limit=limit).status_code == 422


def test_list_rejects_an_unknown_status(client) -> None:
    assert contracts(client, status="deleted").status_code == 422


# --- GET /v1/audit/events -----------------------------------------------


def seed_event(
    repository,
    event_type: str = "contract.registered",
    occurred_at: int = FROZEN_NOW,
    **fields,
) -> None:
    """Append straight to the fake, so window tests can control occurred_at."""
    repository._seq += 1
    repository.events.append(
        AuditEvent(
            seq=repository._seq,
            event_type=event_type,
            occurred_at=occurred_at,
            **fields,
        )
    )


def event_seqs(response) -> List[int]:
    return [e["seq"] for e in response.json()["items"]]


def feed(client, **params):
    return client.get("/v1/audit/events", params=params)


def test_feed_returns_an_object_not_an_array(client) -> None:
    assert feed(client).json() == {
        "items": [],
        "page": 1,
        "limit": 50,
        "total": 0,
        "total_pages": 0,
    }


def test_feed_is_newest_first(client, repository) -> None:
    for _ in range(3):
        seed_event(repository)
    assert event_seqs(feed(client)) == [3, 2, 1]


def test_feed_spans_every_contract(client) -> None:
    client.post("/v1/contracts", json=register_body("a"))
    client.post("/v1/contracts", json=register_body("b"))
    client.patch("/v1/contracts/b/status", json={"status": "revoked"})
    body = feed(client).json()
    assert body["total"] == 3
    assert {e["jti"] for e in body["items"]} == {"a", "b"}


def test_feed_paging_visits_every_event_exactly_once(client, repository) -> None:
    for _ in range(7):
        seed_event(repository)
    pages = walk(client, "/v1/audit/events", limit=3)
    assert [len(p["items"]) for p in pages] == [3, 3, 1]
    assert [e["seq"] for e in every_item(pages)] == [7, 6, 5, 4, 3, 2, 1]


def test_a_feed_page_past_the_end_is_empty_not_an_error(client, repository) -> None:
    for _ in range(4):
        seed_event(repository)
    r = feed(client, page=10, limit=2)
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert (r.json()["total"], r.json()["total_pages"]) == (4, 2)


def test_the_feed_total_agrees_with_the_rows_the_filters_return(
    client, repository
) -> None:
    for i in range(9):
        seed_event(
            repository,
            event_type=(
                "contract.status_change_rejected" if i % 3 else "contract.registered"
            ),
            occurred_at=100 + i,
            consumer_id="alice" if i % 2 else "bob",
            to_status="active",
        )
    for params in (
        {},
        {"event_type": "contract.status_change_rejected"},
        {"consumer_id": "alice"},
        {"since": 102, "until": 107},
        {
            "event_type": "contract.status_change_rejected",
            "consumer_id": "alice",
            "since": 101,
        },
    ):
        pages = walk(client, "/v1/audit/events", limit=2, **params)
        assert pages[0]["total"] == len(every_item(pages)), params


def test_everyone_who_tried_to_reactivate_a_finished_contract(client) -> None:
    """The query an operator opens this endpoint for."""
    for jti in ("a", "b", "c"):
        client.post("/v1/contracts", json=register_body(jti))
    client.patch("/v1/contracts/a/status", json={"status": "revoked"})
    client.patch("/v1/contracts/b/status", json={"status": "completed"})
    client.patch("/v1/contracts/c/status", json={"status": "cancelled"})
    client.patch("/v1/contracts/a/status", json={"status": "active"})  # refused
    client.patch("/v1/contracts/b/status", json={"status": "active"})  # refused

    body = feed(
        client, event_type="contract.status_change_rejected", to_status="active"
    ).json()
    assert body["total"] == 2
    assert sorted((e["jti"], e["from_status"]) for e in body["items"]) == [
        ("a", "revoked"),
        ("b", "completed"),
    ]


def test_feed_filters(client, repository) -> None:
    seed_event(
        repository, jti="j1", order_id="o1", consumer_id="alice", to_status="active"
    )
    seed_event(
        repository,
        event_type="contract.status_changed",
        jti="j1",
        order_id="o1",
        consumer_id="alice",
        from_status="active",
        to_status="revoked",
    )
    seed_event(
        repository, jti="j2", order_id="o2", consumer_id="bob", to_status="active"
    )

    assert event_seqs(feed(client, event_type="contract.status_changed")) == [2]
    assert event_seqs(feed(client, jti="j1")) == [2, 1]
    assert event_seqs(feed(client, order_id="o2")) == [3]
    assert event_seqs(feed(client, consumer_id="alice")) == [2, 1]
    assert event_seqs(feed(client, from_status="active")) == [2]
    assert event_seqs(feed(client, to_status="active")) == [3, 1]
    assert event_seqs(feed(client, consumer_id="alice", to_status="revoked")) == [2]


def test_an_unknown_event_type_matches_nothing(client, repository) -> None:
    """Free text, not an enum, so new event kinds are not breaking changes."""
    seed_event(repository)
    r = feed(client, event_type="no.such.type")
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_the_window_is_half_open(client, repository) -> None:
    seed_event(repository, occurred_at=99)
    seed_event(repository, occurred_at=100)  # on `since`: in
    seed_event(repository, occurred_at=150)
    seed_event(repository, occurred_at=200)  # on `until`: out
    assert event_seqs(feed(client, since=100, until=200)) == [3, 2]


def test_consecutive_windows_count_a_boundary_event_once(client, repository) -> None:
    seed_event(repository, occurred_at=100)
    seed_event(repository, occurred_at=200)  # exactly on the join
    seed_event(repository, occurred_at=300)
    first = event_seqs(feed(client, since=100, until=200))
    second = event_seqs(feed(client, since=200, until=300))
    assert (first, second) == ([1], [2])


def test_an_empty_window_is_empty_not_an_error(client, repository) -> None:
    seed_event(repository, occurred_at=100)
    r = feed(client, since=100, until=100)
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_an_inverted_window_is_rejected(client) -> None:
    """Always a caller mistake; an empty page would hide it."""
    r = feed(client, since=200, until=100)
    assert r.status_code == 422
    assert "after" in r.json()["detail"]


@pytest.mark.parametrize("page", [0, -1, "two"])
def test_feed_page_must_be_a_positive_number(client, page) -> None:
    assert feed(client, page=page).status_code == 422


@pytest.mark.parametrize("limit", [0, 201])
def test_feed_limit_is_bounded(client, limit) -> None:
    assert feed(client, limit=limit).status_code == 422


def test_feed_rejects_an_unknown_status(client) -> None:
    assert feed(client, to_status="deleted").status_code == 422


def test_history_is_not_paged(client) -> None:
    """One contract's history is bounded, so it returns everything in one
    response — and must not carry paging fields it never fills in."""
    client.post("/v1/contracts", json=register_body())
    assert set(client.get("/v1/contracts/abc-111/history").json()) == {"items"}


# --- who and why: actor and reason ---------------------------------------

ADMIN = "dev-allowlist:admin@example.org"


def history_of(client, jti: str = "abc-111") -> List[dict]:
    return client.get(f"/v1/contracts/{jti}/history").json()["items"]


def revoke(client, jti: str = "abc-111", **extra):
    return client.patch(
        f"/v1/contracts/{jti}/status", json=dict({"status": "revoked"}, **extra)
    )


def test_a_revocation_records_who_and_why(client) -> None:
    client.post("/v1/contracts", json=register_body())
    revoke(client, actor=ADMIN, reason="credentials leaked")
    event = history_of(client)[-1]
    assert (event["event_type"], event["actor"], event["reason"]) == (
        "contract.status_changed",
        ADMIN,
        "credentials leaked",
    )


def test_the_actor_is_not_the_consumer(client) -> None:
    """The confusion this column exists to end. consumer_id is who the
    contract is FOR; actor is who acted on it."""
    client.post("/v1/contracts", json=register_body(consumer_id="dr-rahul"))
    revoke(client, actor=ADMIN)
    event = history_of(client)[-1]
    assert (event["consumer_id"], event["actor"]) == ("dr-rahul", ADMIN)


def test_a_refused_attempt_records_who_tried(client) -> None:
    """Where actor matters most: not "someone tried to reactivate this", but
    who."""
    client.post("/v1/contracts", json=register_body())
    revoke(client, actor=ADMIN)
    r = client.patch(
        "/v1/contracts/abc-111/status",
        json={
            "status": "active",
            "actor": "dev-allowlist:intern@example.org",
            "reason": "customer asked",
        },
    )
    assert r.status_code == 409
    event = history_of(client)[-1]
    assert event["event_type"] == "contract.status_change_rejected"
    assert (event["actor"], event["reason"]) == (
        "dev-allowlist:intern@example.org",
        "customer asked",
    )


def test_actor_stays_optional_for_the_stubs_callers(client) -> None:
    """The e2e script and the docs revoke with {"status"} alone, as the stub
    this service replaces allowed."""
    client.post("/v1/contracts", json=register_body())
    assert revoke(client).status_code == 200
    event = history_of(client)[-1]
    assert (event["actor"], event["reason"]) == (None, None)


def test_a_registration_has_no_actor(client) -> None:
    """The Generator does not say who it is, and an invented attribution would
    be worse than none."""
    client.post("/v1/contracts", json=register_body())
    assert history_of(client)[0]["actor"] is None


@pytest.mark.parametrize(
    "actor",
    [
        ADMIN,
        "dex:jane.doe@example.org",
        "service-account:ops-bot",
        "dex:colons:are:fine:after:the:source",
        "dex:" + "x" * 251,  # 255 characters: exactly the column's width
    ],
)
def test_well_formed_actors_are_accepted(client, actor) -> None:
    client.post("/v1/contracts", json=register_body())
    assert revoke(client, actor=actor).status_code == 200
    assert history_of(client)[-1]["actor"] == actor


@pytest.mark.parametrize(
    "actor",
    [
        "rahul",  # no source: says nothing about how far to trust it
        "dex:",  # no identity
        ":rahul",  # empty source
        "Dex:rahul",  # source must be lowercase, so "dex" and "Dex" never split
        "-dex:rahul",  # source cannot start with a hyphen
        "dex:rahul smith",  # whitespace in the identity
        " dex:rahul",  # leading whitespace
        "dex:" + "x" * 252,  # 256 characters: one over the column
    ],
)
def test_malformed_actors_are_refused_and_leave_no_trace(client, actor) -> None:
    """A 422 is refused before the state machine sees it, so unlike a 409 it
    writes no history: malformed input is not an attempt to change anything."""
    client.post("/v1/contracts", json=register_body())
    before = len(history_of(client))
    assert revoke(client, actor=actor).status_code == 422
    assert len(history_of(client)) == before
    assert client.get("/v1/contracts/abc-111").json()["status"] == "active"


def test_a_reason_is_trimmed(client) -> None:
    client.post("/v1/contracts", json=register_body())
    revoke(client, actor=ADMIN, reason="   credentials leaked \n ")
    assert history_of(client)[-1]["reason"] == "credentials leaked"


def test_a_reason_may_use_its_full_width(client) -> None:
    client.post("/v1/contracts", json=register_body())
    assert revoke(client, actor=ADMIN, reason="x" * 500).status_code == 200


@pytest.mark.parametrize("reason", ["", "   ", "x" * 501])
def test_a_blank_or_oversized_reason_is_refused(client, reason) -> None:
    """Blank would store a reason that says nothing; 501 is one over the
    column."""
    client.post("/v1/contracts", json=register_body())
    assert revoke(client, actor=ADMIN, reason=reason).status_code == 422


def test_the_feed_filters_by_actor(client) -> None:
    """ "Show me everything this admin did" is one query."""
    client.post("/v1/contracts", json=register_body("a"))
    client.post("/v1/contracts", json=register_body("b"))
    revoke(client, "a", actor=ADMIN, reason="leak")
    revoke(client, "b", actor="dev-allowlist:other@example.org")

    body = feed(client, actor=ADMIN).json()
    assert body["total"] == 1
    assert [(e["jti"], e["actor"], e["reason"]) for e in body["items"]] == [
        ("a", ADMIN, "leak")
    ]
