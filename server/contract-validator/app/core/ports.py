"""Ports — interfaces the validation use-case depends on."""

from typing import Protocol


class JWKSResolver(Protocol):
    """Looks up a public key by `kid` from the issuing node's JWKS endpoint."""

    async def get_public_pem(self, iss: str, kid: str) -> bytes:
        """Return the PEM-encoded public key for verifying tokens from `iss`."""
        ...


class ClearingHouseReader(Protocol):
    """Reads contract status from the local Clearing House."""

    async def get_status(self, jti: str) -> str:
        """Return the current status string ('active', 'revoked', 'cancelled', ...)."""
        ...
