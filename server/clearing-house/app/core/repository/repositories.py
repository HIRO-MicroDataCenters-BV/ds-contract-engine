"""The storage interface.

A description of what any storage implementation must be able to do. No SQL,
no database, no behaviour — every method body is `...`. The implementation
lives in sql_repository.py.

Three things this layer deliberately does NOT do, and which apply to every
implementation:

* No business rules. "A revoked contract cannot be reactivated" is a decision,
  not storage, and it belongs above — where it can be tested without a
  database, and overridden by an admin tool that legitimately needs to.
* No HTTP. Methods return None for "not found"; the route decides that means
  404. Raising HTTPException here would make this layer unusable from a CLI,
  a background task or a test, and would let storage choose a status code it
  cannot possibly reason about.
* No sessions escape. Each method opens one, commits, closes. Callers never
  see a session and cannot leak one.

The cost of that last rule is that two calls cannot share a transaction, which
is why register() and set_status() are specified to write their own audit
event. A contract that exists with no record of being created would be worse
than no contract at all.
"""

from typing import List, Optional

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.models import AuditEvent, Contract
from app.database import Database

# Event types every implementation is expected to write.
EVENT_REGISTERED = "contract.registered"
EVENT_STATUS_CHANGED = "contract.status_changed"


@dataclass(frozen=True)
class ContractQuery:
    """Which contracts to list. Every field is optional; unset means "any".

    Expiry is expressed as bounds on exp rather than as "expired or not",
    because deciding what expired means needs a clock, and a clock is a
    business concern — see ContractUsecases.list_contracts.
    """

    status: Optional[str] = None
    consumer_id: Optional[str] = None
    order_id: Optional[str] = None
    exp_at_or_before: Optional[int] = None
    exp_after: Optional[int] = None


@dataclass(frozen=True)
class EventQuery:
    """Which history entries to list. Every field is optional; unset means "any".

    The time window is half-open — occurred_at_or_after inclusive,
    occurred_before exclusive — and the names say so, because the boundary is
    the whole point: consecutive windows then never count an event twice.
    """

    event_type: Optional[str] = None
    jti: Optional[str] = None
    order_id: Optional[str] = None
    consumer_id: Optional[str] = None
    actor: Optional[str] = None
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    occurred_at_or_after: Optional[int] = None
    occurred_before: Optional[int] = None


class Repositories(ABC):
    def __init__(self, database: Database) -> None: ...

    @abstractmethod
    async def register(self, contract: Contract) -> Contract:
        """Store a newly minted contract, and record that it happened.

        Returns the stored contract. If the jti is already known, returns the
        existing row rather than raising: the Generator makes one attempt with
        no retry budget, and the stub this service replaces silently
        overwrites, so a duplicate must not become an error.
        """
        ...

    @abstractmethod
    async def get(self, jti: str) -> Optional[Contract]:
        """Read one contract. None if unknown.

        The hot path: the Contract Validator calls this on every data access
        and blocks on the answer.
        """
        ...

    @abstractmethod
    async def set_status(
        self,
        jti: str,
        status: str,
        changed_at: int,
        actor: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[Contract]:
        """Move a contract to a new status, and record that it happened.

        Returns the updated contract, or None if the jti is unknown. Performs
        no validation of the transition — see the module docstring.

        actor and reason go on the history entry this writes, not on the
        contract: the contract holds current state, the history holds who
        changed it and why.
        """
        ...

    @abstractmethod
    async def append_event(self, event: AuditEvent) -> AuditEvent:
        """Append one history entry on its own.

        register() and set_status() already record the change they make, so
        this is for events with no corresponding contract change — a refused
        status transition being the case that needs it. Returns the event with
        its assigned seq.
        """
        ...

    @abstractmethod
    async def events_for_jti(self, jti: str) -> List[AuditEvent]:
        """History of one contract, oldest first."""
        ...

    @abstractmethod
    async def events_for_order(self, order_id: str) -> List[AuditEvent]:
        """History of a whole order, oldest first.

        One order can span several contracts, so this is broader than
        events_for_jti.
        """
        ...

    @abstractmethod
    async def list_contracts(
        self, query: ContractQuery, limit: int, offset: int = 0
    ) -> List[Contract]:
        """Contracts matching query, newest first: skip `offset`, return up
        to `limit`.

        The order must be total — (registered_at, jti), both descending.
        registered_at is whole seconds and the Generator mints several per
        second, so on its own it leaves ties with no defined order, and with
        offset paging an undefined order means a row can land on two pages or
        on none, even when nothing new has arrived.
        """
        ...

    @abstractmethod
    async def count_contracts(self, query: ContractQuery) -> int:
        """How many contracts match query.

        Must apply exactly the same conditions as list_contracts, or the
        "showing 51–100 of N" that the UI builds from it will lie.
        """
        ...

    @abstractmethod
    async def list_events(
        self, query: EventQuery, limit: int, offset: int = 0
    ) -> List[AuditEvent]:
        """History entries matching query, newest first by seq: skip
        `offset`, return up to `limit`.

        seq alone is a total order — unique, and only ever increasing — so
        unlike contracts no tiebreaker is needed.
        """
        ...

    @abstractmethod
    async def count_events(self, query: EventQuery) -> int:
        """How many history entries match query. Same conditions as
        list_events, for the same reason as count_contracts."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check connectivity to the database."""
        ...
