"""Ports (interfaces) the use-case depends on.

Concrete implementations live in app/adapters/. This indirection lets the
use-case be tested with stubs and lets the wire-level concerns evolve
independently.
"""

from typing import Protocol


class SigningKeyService(Protocol):
    """Handles loading and using the node's Ed25519 signing key."""

    def kid(self) -> str:
        """Return the active key id (the `kid` to put in the JWT header)."""
        ...

    def sign(self, data: bytes) -> bytes:
        """Sign `data` with the active private key and return the raw signature."""
        ...

    def public_jwk(self) -> dict:
        """Return the active public key in JWK form (for the JWKS endpoint)."""
        ...

    def public_pem(self) -> bytes:
        """Return the active public key in PEM form (for self-verification)."""
        ...


class ClearingHouse(Protocol):
    """Handles contract registration in the per-node Clearing House."""

    async def register(
        self, jti: str, order_id: str, consumer_id: str, iat: int, exp: int
    ) -> None:
        """Register a freshly minted contract as `active`. Raises on failure."""
        ...
