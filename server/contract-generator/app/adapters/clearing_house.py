"""Clearing House adapter — registers freshly minted contracts.

Talks to the per-node Clearing House via HTTP. The CH is expected to expose:

    POST /v1/contracts  { jti, order_id, status: "active", consumer_id, iat, exp }

The adapter is fail-fast: a non-2xx response raises ClearingHouseError, which
the use-case lets bubble up — we'd rather refuse the mint than ship an
unregistered token.
"""

import logging

import httpx

from app.core.exceptions import ClearingHouseError

logger = logging.getLogger("ds_contract_generator.clearing_house")


class HttpClearingHouse:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def register(
        self, jti: str, order_id: str, consumer_id: str, iat: int, exp: int
    ) -> None:
        url = f"{self._base_url}/v1/contracts"
        body = {
            "jti": jti,
            "order_id": order_id,
            "status": "active",
            "consumer_id": consumer_id,
            "iat": iat,
            "exp": exp,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=body)
        except httpx.RequestError as exc:
            logger.error("Clearing House unreachable at %s: %s", url, exc)
            raise ClearingHouseError(f"Clearing House unreachable: {exc}") from exc

        if resp.status_code >= 300:
            logger.error(
                "Clearing House refused registration jti=%s status=%s body=%s",
                jti,
                resp.status_code,
                resp.text,
            )
            raise ClearingHouseError(
                f"Clearing House refused registration: HTTP {resp.status_code}"
            )
        logger.info("Clearing House registered jti=%s", jti)


class StubClearingHouse:
    """In-memory stub — used when no real Clearing House is reachable.

    Useful for local development and for unit tests. Logs every registration.
    """

    def __init__(self) -> None:
        self._registrations: dict[str, dict] = {}

    async def register(
        self, jti: str, order_id: str, consumer_id: str, iat: int, exp: int
    ) -> None:
        self._registrations[jti] = {
            "jti": jti,
            "order_id": order_id,
            "status": "active",
            "consumer_id": consumer_id,
            "iat": iat,
            "exp": exp,
        }
        logger.info("StubClearingHouse: registered jti=%s order_id=%s", jti, order_id)

    @property
    def registrations(self) -> dict[str, dict]:
        return dict(self._registrations)
