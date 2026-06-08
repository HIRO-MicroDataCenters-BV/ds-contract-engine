"""In-memory contract registry.

This is the stub's entire state. Lost on pod restart — fine for testing.
"""

import logging
from threading import Lock
from typing import Optional

logger = logging.getLogger("ds_clearing_house_stub.storage")


class ContractStore:
    """Thread-safe in-memory store for contract registrations."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._contracts: dict[str, dict] = {}

    def register(
        self,
        jti: str,
        order_id: str,
        consumer_id: str,
        iat: int,
        exp: int,
    ) -> dict:
        with self._lock:
            record = {
                "jti": jti,
                "order_id": order_id,
                "status": "active",
                "consumer_id": consumer_id,
                "iat": iat,
                "exp": exp,
            }
            self._contracts[jti] = record
            logger.info("registered jti=%s order_id=%s", jti, order_id)
            return record

    def get(self, jti: str) -> Optional[dict]:
        with self._lock:
            return self._contracts.get(jti)

    def list_all(self) -> list[dict]:
        with self._lock:
            return list(self._contracts.values())

    def update_status(self, jti: str, status: str) -> Optional[dict]:
        with self._lock:
            record = self._contracts.get(jti)
            if record is None:
                return None
            record["status"] = status
            logger.info("status_changed jti=%s status=%s", jti, status)
            return record
