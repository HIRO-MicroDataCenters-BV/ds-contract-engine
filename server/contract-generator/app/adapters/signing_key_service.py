"""Local Ed25519 signing key adapter.

Loads (or generates on first run) a PEM-encoded Ed25519 private key from disk.
The corresponding public key is published via the JWKS endpoint.

In production this adapter would be replaced by one that talks to a remote
signing-key service (Vault, KMS, etc.) — the SigningKeyService Protocol stays
the same.
"""

import base64
import logging
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

logger = logging.getLogger("ds_contract_generator.signing_key")


class LocalEd25519SigningKey:
    """Ed25519 signing-key adapter backed by a PEM file on disk."""

    def __init__(self, private_key_path: str, kid: str) -> None:
        self._path = Path(private_key_path)
        self._kid = kid
        self._private = self._load_or_generate()

    def kid(self) -> str:
        return self._kid

    def private_pem(self) -> bytes:
        return self._private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def public_pem(self) -> bytes:
        return self._private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def public_jwk(self) -> dict:
        """Return the public key in JWK form for /.well-known/jwks.json."""
        raw = self._private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        x = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
        return {
            "kty": "OKP",
            "crv": "Ed25519",
            "use": "sig",
            "alg": "EdDSA",
            "kid": self._kid,
            "x": x,
        }

    def sign(self, data: bytes) -> bytes:
        return self._private.sign(data)

    # -- internals --------------------------------------------------------

    def _load_or_generate(self) -> Ed25519PrivateKey:
        if self._path.exists():
            with self._path.open("rb") as fh:
                key = serialization.load_pem_private_key(fh.read(), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise RuntimeError(
                    f"Key at {self._path} is not Ed25519 (got {type(key).__name__})."
                )
            logger.info("Loaded Ed25519 signing key from %s", self._path)
            return key

        # Generate on first run — convenience for development.
        logger.warning(
            "No signing key found at %s — generating a fresh one. "
            "Do NOT use this in production.",
            self._path,
        )
        key = Ed25519PrivateKey.generate()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("wb") as fh:
            fh.write(
                key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
        return key
