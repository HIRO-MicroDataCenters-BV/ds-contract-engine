"""Clearing House reader adapter.

Queries `GET <CH>/v1/contracts/{jti}` and returns the `status` string.
"""

import logging

import httpx

from app.core.exceptions import ClearingHouseError

logger = logging.getLogger("ds_contract_validator.clearing_house")


class HttpClearingHouseReader:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def get_status(self, jti: str) -> str:
        url = f"{self._base_url}/v1/contracts/{jti}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url)
        except httpx.RequestError as exc:
            raise ClearingHouseError(f"Clearing House unreachable: {exc}") from exc

        if resp.status_code == 404:
            return "not_registered"
        if resp.status_code >= 300:
            raise ClearingHouseError(
                f"Clearing House returned HTTP {resp.status_code}"
            )

        try:
            body = resp.json()
        except ValueError as exc:
            raise ClearingHouseError(
                f"Clearing House response not JSON: {exc}"
            ) from exc

        status = body.get("status")
        if not isinstance(status, str):
            raise ClearingHouseError("Clearing House response missing 'status'")
        return status
