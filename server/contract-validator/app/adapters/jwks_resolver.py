"""JWKS resolver adapter.

Fetches a node's public keys from `https://<iss>/.well-known/jwks.json`
(or a configured base URL template) and caches them. Returns the public key
in PEM form so PyJWT can verify with `algorithms=["EdDSA"]`.
"""

import base64
import logging
from typing import Optional

import httpx
from cachetools import TTLCache
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.core.exceptions import JWKSError

logger = logging.getLogger("ds_contract_validator.jwks")


class HttpJWKSResolver:
    def __init__(
        self,
        cache_ttl_seconds: int = 3600,
        timeout_seconds: float = 5.0,
        base_url_template: Optional[str] = None,
    ) -> None:
        self._cache: TTLCache = TTLCache(maxsize=128, ttl=cache_ttl_seconds)
        self._timeout = timeout_seconds
        # Empty / None template = derive URL from iss directly:
        # https://<iss>/.well-known/jwks.json
        self._base_url_template = base_url_template or ""

    async def get_public_pem(self, iss: str, kid: str) -> bytes:
        cache_key = (iss, kid)
        if cache_key in self._cache:
            return self._cache[cache_key]

        url = self._jwks_url_for(iss)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                jwks = resp.json()
        except httpx.RequestError as exc:
            raise JWKSError(f"JWKS unreachable at {url}: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise JWKSError(f"JWKS returned HTTP {exc.response.status_code}") from exc
        except ValueError as exc:
            raise JWKSError(f"JWKS not valid JSON: {exc}") from exc

        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                pem = self._jwk_to_pem(key)
                self._cache[cache_key] = pem
                return pem

        raise JWKSError(f"kid '{kid}' not found in JWKS at {url}")

    # -- internals --------------------------------------------------------

    def _jwks_url_for(self, iss: str) -> str:
        if self._base_url_template:
            base = self._base_url_template.rstrip("/")
        else:
            # Default: derive from iss. iss is a hostname, not necessarily a URL.
            base = iss if iss.startswith("http") else f"https://{iss}"
        return f"{base}/.well-known/jwks.json"

    @staticmethod
    def _jwk_to_pem(jwk: dict) -> bytes:
        if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519":
            raise JWKSError(
                f"Unsupported key type kty={jwk.get('kty')} crv={jwk.get('crv')}"
            )
        x = jwk.get("x")
        if not x:
            raise JWKSError("JWK missing x parameter")
        # base64url-decode (with padding)
        padded = x + "=" * (-len(x) % 4)
        raw = base64.urlsafe_b64decode(padded)
        public_key = Ed25519PublicKey.from_public_bytes(raw)
        return public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
