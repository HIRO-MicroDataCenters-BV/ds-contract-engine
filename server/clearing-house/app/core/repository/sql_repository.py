"""SQLAlchemy implementation of the storage interface.

Works unchanged on SQLite and PostgreSQL: nothing here is engine-specific.
See repositories.py for what this is required to do, and for the three rules
it follows.
"""

from typing import List, Optional

import logging

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.elements import ColumnElement

from app.core.models import AuditEvent, Contract
from app.core.repository.repositories import (
    EVENT_REGISTERED,
    EVENT_STATUS_CHANGED,
    ContractQuery,
    EventQuery,
    Repositories,
)
from app.database import Database

logger = logging.getLogger(__name__)


class SqlRepository(Repositories):
    def __init__(self, database: Database) -> None:
        self.database = database

    # --- writes ---------------------------------------------------------

    async def register(self, contract: Contract) -> Contract:
        try:
            async with self.database.session() as session:
                existing = await session.get(Contract, contract.jti)
                if existing is not None:
                    logger.info(
                        "Contract %s already registered — returning existing",
                        contract.jti,
                    )
                    return existing

                session.add(contract)
                session.add(
                    AuditEvent(
                        event_type=EVENT_REGISTERED,
                        jti=contract.jti,
                        order_id=contract.order_id,
                        consumer_id=contract.consumer_id,
                        # No from_status: nothing preceded registration.
                        to_status=contract.status,
                        occurred_at=contract.registered_at,
                        detail=f"status={contract.status} exp={contract.exp}",
                    )
                )
                # One commit for both rows: a contract with no record of its
                # creation is a hole in the audit trail.
                await session.commit()
                logger.info(
                    "Registered contract %s order=%s",
                    contract.jti,
                    contract.order_id,
                )
                return contract
        except SQLAlchemyError as e:
            logger.error("Database error registering %s: %s", contract.jti, e)
            raise

    async def set_status(
        self,
        jti: str,
        status: str,
        changed_at: int,
        actor: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[Contract]:
        try:
            async with self.database.session() as session:
                contract = await session.get(Contract, jti)
                if contract is None:
                    logger.info("Cannot set status: %s is not registered", jti)
                    return None

                previous = contract.status
                contract.status = status
                contract.status_changed_at = changed_at

                session.add(
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
                await session.commit()
                logger.info(
                    "Contract %s status %s -> %s actor=%s", jti, previous, status, actor
                )
                return contract
        except SQLAlchemyError as e:
            logger.error("Database error setting status on %s: %s", jti, e)
            raise

    async def append_event(self, event: AuditEvent) -> AuditEvent:
        try:
            async with self.database.session() as session:
                session.add(event)
                await session.commit()
                return event
        except SQLAlchemyError as e:
            logger.error("Database error appending %s: %s", event.event_type, e)
            raise

    # --- reads ----------------------------------------------------------

    async def get(self, jti: str) -> Optional[Contract]:
        try:
            async with self.database.session() as session:
                return await session.get(Contract, jti)
        except SQLAlchemyError as e:
            logger.error("Database error reading %s: %s", jti, e)
            raise

    async def events_for_jti(self, jti: str) -> List[AuditEvent]:
        return await self._events(AuditEvent.jti == jti, f"jti={jti}")

    async def events_for_order(self, order_id: str) -> List[AuditEvent]:
        return await self._events(
            AuditEvent.order_id == order_id, f"order_id={order_id}"
        )

    async def _events(
        self, condition: ColumnElement[bool], described: str
    ) -> List[AuditEvent]:
        try:
            async with self.database.session() as session:
                result = await session.execute(
                    # seq, not occurred_at: two events can share a timestamp,
                    # and seq is the only unambiguous ordering.
                    select(AuditEvent)
                    .where(condition)
                    .order_by(AuditEvent.seq)
                )
                return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error("Database error reading events for %s: %s", described, e)
            raise

    # --- listing, for the admin console -----------------------------------

    @staticmethod
    def _contract_conditions(query: ContractQuery) -> List[ColumnElement[bool]]:
        """The WHERE clause for a contract query, shared by list and count.

        Built in one place so the two cannot disagree. A count that applied
        one filter fewer than the list would make "showing 51–100 of N" wrong
        in a way nobody would notice.
        """
        conditions: List[ColumnElement[bool]] = []
        if query.status is not None:
            conditions.append(Contract.status == query.status)
        if query.consumer_id is not None:
            conditions.append(Contract.consumer_id == query.consumer_id)
        if query.order_id is not None:
            conditions.append(Contract.order_id == query.order_id)
        if query.exp_at_or_before is not None:
            conditions.append(Contract.exp <= query.exp_at_or_before)
        if query.exp_after is not None:
            conditions.append(Contract.exp > query.exp_after)
        return conditions

    async def list_contracts(
        self, query: ContractQuery, limit: int, offset: int = 0
    ) -> List[Contract]:
        stmt = (
            select(Contract)
            .where(*self._contract_conditions(query))
            # jti as the tiebreaker is what makes the order total. Without it,
            # contracts registered in the same second have no defined order,
            # and offset paging can then show one twice or never.
            .order_by(Contract.registered_at.desc(), Contract.jti.desc())
            .limit(limit)
            .offset(offset)
        )
        try:
            async with self.database.session() as session:
                result = await session.execute(stmt)
                return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error("Database error listing contracts: %s", e)
            raise

    async def count_contracts(self, query: ContractQuery) -> int:
        stmt = (
            select(func.count())
            .select_from(Contract)
            .where(*self._contract_conditions(query))
        )
        try:
            async with self.database.session() as session:
                return int((await session.execute(stmt)).scalar_one())
        except SQLAlchemyError as e:
            logger.error("Database error counting contracts: %s", e)
            raise

    @staticmethod
    def _event_conditions(query: EventQuery) -> List[ColumnElement[bool]]:
        """The WHERE clause for a history query, shared by list and count."""
        conditions: List[ColumnElement[bool]] = []
        if query.event_type is not None:
            conditions.append(AuditEvent.event_type == query.event_type)
        if query.jti is not None:
            conditions.append(AuditEvent.jti == query.jti)
        if query.order_id is not None:
            conditions.append(AuditEvent.order_id == query.order_id)
        if query.consumer_id is not None:
            conditions.append(AuditEvent.consumer_id == query.consumer_id)
        if query.actor is not None:
            conditions.append(AuditEvent.actor == query.actor)
        if query.from_status is not None:
            conditions.append(AuditEvent.from_status == query.from_status)
        if query.to_status is not None:
            conditions.append(AuditEvent.to_status == query.to_status)
        if query.occurred_at_or_after is not None:
            conditions.append(AuditEvent.occurred_at >= query.occurred_at_or_after)
        if query.occurred_before is not None:
            conditions.append(AuditEvent.occurred_at < query.occurred_before)
        return conditions

    async def list_events(
        self, query: EventQuery, limit: int, offset: int = 0
    ) -> List[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(*self._event_conditions(query))
            # Filtered on occurred_at but ordered by seq, deliberately. seq is
            # the order the ledger recorded things in, and it is total;
            # occurred_at can tie, and once other services report events with
            # their own timestamps it can also arrive out of order.
            .order_by(AuditEvent.seq.desc())
            .limit(limit)
            .offset(offset)
        )
        try:
            async with self.database.session() as session:
                result = await session.execute(stmt)
                return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error("Database error listing events: %s", e)
            raise

    async def count_events(self, query: EventQuery) -> int:
        stmt = (
            select(func.count())
            .select_from(AuditEvent)
            .where(*self._event_conditions(query))
        )
        try:
            async with self.database.session() as session:
                return int((await session.execute(stmt)).scalar_one())
        except SQLAlchemyError as e:
            logger.error("Database error counting events: %s", e)
            raise

    async def health_check(self) -> bool:
        try:
            async with self.database.session() as session:
                await session.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError as e:
            logger.error("Database health check failed: %s", e)
            return False
