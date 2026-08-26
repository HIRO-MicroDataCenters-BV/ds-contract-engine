"""SQLAlchemy implementation of the storage interface.

Works unchanged on SQLite and PostgreSQL: nothing here is engine-specific.
See repositories.py for what this is required to do, and for the three rules
it follows.
"""

from typing import List, Optional

import logging

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.elements import ColumnElement

from app.core.models import AuditEvent, Contract
from app.core.repository.repositories import (
    EVENT_REGISTERED,
    EVENT_STATUS_CHANGED,
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
        self, jti: str, status: str, changed_at: int
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
                        from_status=previous,
                        to_status=status,
                        occurred_at=changed_at,
                        detail=f"{previous} -> {status}",
                    )
                )
                await session.commit()
                logger.info("Contract %s status %s -> %s", jti, previous, status)
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

    async def health_check(self) -> bool:
        try:
            async with self.database.session() as session:
                await session.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError as e:
            logger.error("Database health check failed: %s", e)
            return False
