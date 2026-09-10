"""Business rules for the Clearing House.

Sits between the routes (which speak HTTP) and the repository (which speaks
SQL) and owns the decisions neither should make:

* whether a status change is permitted at all
* what a newly registered contract looks like
* what the current time is — and so what "expired" means

No SQL, no HTTP. Raises plain exceptions; the route decides the status code.
"""

from typing import Callable, List, NamedTuple, Optional

import logging
import time

from app.core.exceptions import IllegalStatusTransition
from app.core.models import STATUS_ACTIVE, AuditEvent, Contract
from app.core.repository import (
    ContractQuery,
    EventQuery,
    Repositories,
)
from app.core.status import can_transition

logger = logging.getLogger(__name__)

# Written when a status change is refused. A rejected attempt to reactivate a
# revoked permit is precisely what an auditor wants to see, and a log that
# records only successes hides it.
EVENT_STATUS_REJECTED = "contract.status_change_rejected"

# Returns the current Unix time in seconds. Injected so tests can freeze it:
# every stored row carries a timestamp, and being unable to assert them
# exactly would leave a real gap in an audit trail's test coverage.
Clock = Callable[[], int]


def _system_clock() -> int:
    return int(time.time())


class ContractListing(NamedTuple):
    """One page of contracts, and how many match in total."""

    items: List[Contract]
    total: int


class EventListing(NamedTuple):
    """One page of history entries, and how many match in total."""

    items: List[AuditEvent]
    total: int


def _offset(page: int, limit: int) -> int:
    """Rows to skip to reach `page`. Pages count from 1."""
    return (page - 1) * limit


class ContractUsecases:
    def __init__(self, repository: Repositories, clock: Optional[Clock] = None) -> None:
        self.repository = repository
        self.clock = clock or _system_clock

    async def register(
        self,
        jti: str,
        order_id: str,
        consumer_id: str,
        iat: int,
        exp: int,
    ) -> Contract:
        """Record a newly minted contract as active.

        Idempotent, because the Generator makes one attempt with no retry
        budget: registering the same jti twice returns the existing contract
        rather than failing.
        """
        now = self.clock()
        contract = Contract(
            jti=jti,
            order_id=order_id,
            consumer_id=consumer_id,
            # Every contract starts active. The caller does not get to choose:
            # a contract that arrived already revoked would be meaningless.
            status=STATUS_ACTIVE,
            iat=iat,
            exp=exp,
            registered_at=now,
            status_changed_at=now,
        )
        return await self.repository.register(contract)

    async def read(self, jti: str) -> Optional[Contract]:
        """Fetch one contract. None if unknown — the route turns that into 404.

        No rules here; the Validator asks this on every data access and any
        work done in this path is paid for on every read.
        """
        return await self.repository.get(jti)

    async def change_status(self, jti: str, new_status: str) -> Optional[Contract]:
        """Move a contract to a new status, if the state machine allows it.

        Returns None if the jti is unknown. Raises IllegalStatusTransition if
        the change is forbidden — and records the attempt before raising.
        """
        contract = await self.repository.get(jti)
        if contract is None:
            return None

        if not can_transition(contract.status, new_status):
            logger.warning(
                "Refused status change on %s: %s -> %s",
                jti,
                contract.status,
                new_status,
            )
            await self._record_rejection(contract, new_status)
            raise IllegalStatusTransition(jti, contract.status, new_status)

        return await self.repository.set_status(jti, new_status, self.clock())

    async def history(self, jti: str) -> Optional[List[AuditEvent]]:
        """Everything that happened to one contract, oldest first.

        None means no such contract, which is not the same as a contract with
        no events — registration always writes one, so an empty list would be
        a bug rather than a legitimate answer. Keeping the distinction here
        rather than in the route lets it stay a 404, matching
        GET /v1/contracts/{jti}, without the route knowing why.
        """
        contract = await self.repository.get(jti)
        if contract is None:
            return None
        return await self.repository.events_for_jti(jti)

    async def list_contracts(
        self,
        *,
        page: int,
        limit: int,
        status: Optional[str] = None,
        consumer_id: Optional[str] = None,
        order_id: Optional[str] = None,
        expired: Optional[bool] = None,
    ) -> ContractListing:
        """Contracts, newest first, one page at a time. Pages count from 1.

        `expired` is deliberately separate from `status`. A contract can be
        `active` and already past its exp — the Validator checks the two
        independently — so folding expiry into status would make "active"
        quietly mean something the stored value does not.
        """
        now = self.clock()

        # RFC 7519 §4.1.4: a token MUST NOT be accepted "on or after" its exp.
        # So expired means exp <= now, and the boundary second is expired.
        #
        # The Validator adds a few seconds of leeway for clock skew, so for
        # that brief window a contract listed here as expired may still
        # validate. Leeway is a tolerance applied when checking, not a state,
        # and this reports the state.
        query = ContractQuery(
            status=status,
            consumer_id=consumer_id,
            order_id=order_id,
            exp_at_or_before=now if expired is True else None,
            exp_after=now if expired is False else None,
        )

        # Two queries, so a contract registered between them can leave total
        # one ahead of the rows. Harmless for a screen a person is reading —
        # the same trade offset paging already makes when rows arrive between
        # page loads — and not worth a transaction to close.
        items = await self.repository.list_contracts(query, limit, _offset(page, limit))
        total = await self.repository.count_contracts(query)
        return ContractListing(items, total)

    async def list_events(
        self,
        *,
        page: int,
        limit: int,
        event_type: Optional[str] = None,
        jti: Optional[str] = None,
        order_id: Optional[str] = None,
        consumer_id: Optional[str] = None,
        from_status: Optional[str] = None,
        to_status: Optional[str] = None,
        occurred_at_or_after: Optional[int] = None,
        occurred_before: Optional[int] = None,
    ) -> EventListing:
        """The ledger across every contract, newest first. Pages count from 1."""
        query = EventQuery(
            event_type=event_type,
            jti=jti,
            order_id=order_id,
            consumer_id=consumer_id,
            from_status=from_status,
            to_status=to_status,
            occurred_at_or_after=occurred_at_or_after,
            occurred_before=occurred_before,
        )
        items = await self.repository.list_events(query, limit, _offset(page, limit))
        total = await self.repository.count_events(query)
        return EventListing(items, total)

    async def order_history(self, order_id: str) -> List[AuditEvent]:
        """Everything that happened across a whole order.

        One order can span several contracts — one per node — so this is
        broader than history().
        """
        return await self.repository.events_for_order(order_id)

    async def _record_rejection(self, contract: Contract, requested: str) -> None:
        """Log the refused attempt, without letting it break the refusal.

        If the audit write fails we still want the caller to get their 409:
        failing to record a rejection must not turn into accidentally
        allowing it.
        """
        try:
            await self.repository.append_event(
                AuditEvent(
                    event_type=EVENT_STATUS_REJECTED,
                    jti=contract.jti,
                    order_id=contract.order_id,
                    consumer_id=contract.consumer_id,
                    # The transition that was asked for and refused — recorded
                    # exactly like one that succeeded, so a query for "attempts
                    # to reach active" finds both.
                    from_status=contract.status,
                    to_status=requested,
                    occurred_at=self.clock(),
                    detail=f"{contract.status} -> {requested} (refused)",
                )
            )
        except Exception as e:  # noqa: BLE001 — deliberately broad, see docstring
            logger.error(
                "Could not record rejected status change on %s: %s", contract.jti, e
            )
