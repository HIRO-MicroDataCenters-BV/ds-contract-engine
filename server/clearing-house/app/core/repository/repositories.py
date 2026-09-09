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

from app.core.models import AuditEvent, Contract
from app.database import Database

# Event types every implementation is expected to write.
EVENT_REGISTERED = "contract.registered"
EVENT_STATUS_CHANGED = "contract.status_changed"


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
        self, jti: str, status: str, changed_at: int
    ) -> Optional[Contract]:
        """Move a contract to a new status, and record that it happened.

        Returns the updated contract, or None if the jti is unknown. Performs
        no validation of the transition — see the module docstring.
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
    async def health_check(self) -> bool:
        """Check connectivity to the database."""
        ...
