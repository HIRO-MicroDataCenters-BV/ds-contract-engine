"""Contract generation use-case.

Pure orchestration — accepts a request, builds the payload, signs, self-verifies,
registers with the Clearing House, returns the token. No HTTP concerns leak in.
"""

import logging
import time
import uuid
from typing import Tuple

import jwt

from app.core.entities import (
    ContractGenerationRequest,
    ContractPayload,
    CredentialSubject,
    VerifiableCredential,
)
from app.core.exceptions import (
    SelfVerificationError,
    SigningError,
    TooManyItemsError,
)
from app.core.ports import ClearingHouse, SigningKeyService

logger = logging.getLogger("ds_contract_generator.usecases")


class GenerateContractUsecase:
    def __init__(
        self,
        node_id: str,
        signing_key_service: SigningKeyService,
        clearing_house: ClearingHouse,
        default_ttl_seconds: int = 3600,
        max_items_per_contract: int = 50,
    ) -> None:
        self._node_id = node_id
        self._signing = signing_key_service
        self._ch = clearing_house
        self._default_ttl = default_ttl_seconds
        self._max_items = max_items_per_contract

    async def execute(self, request: ContractGenerationRequest) -> Tuple[str, str, int]:
        """Mint a contract.

        Returns: (token, jti, exp)
        """
        if len(request.items) > self._max_items:
            raise TooManyItemsError(
                f"Request bundles {len(request.items)} items "
                f"(max {self._max_items})."
            )

        now = int(time.time())
        ttl = request.ttl_seconds if request.ttl_seconds is not None else self._default_ttl
        jti = str(uuid.uuid4())
        exp = now + ttl

        payload = ContractPayload(
            jti=jti,
            iss=self._node_id,
            aud=self._node_id,
            sub=request.consumer_id,
            iat=now,
            exp=exp,
            order_id=request.order_id,
            vc=VerifiableCredential(
                credentialSubject=CredentialSubject(catalogItem=request.items)
            ),
        )

        token = self._sign(payload)
        self._self_verify(token)
        await self._ch.register(
            jti=jti,
            order_id=request.order_id,
            consumer_id=request.consumer_id,
            iat=now,
            exp=exp,
        )

        logger.info(
            "contract.generated jti=%s order_id=%s consumer=%s items=%d",
            jti,
            request.order_id,
            request.consumer_id,
            len(request.items),
        )
        return token, jti, exp

    # -- internals --------------------------------------------------------

    def _sign(self, payload: ContractPayload) -> str:
        try:
            kid = self._signing.kid()
            # PyJWT will call into our private key via cryptography. We pass the
            # PEM-loaded private key object via SigningKeyService's adapter.
            from app.adapters.signing_key_service import LocalEd25519SigningKey

            if not isinstance(self._signing, LocalEd25519SigningKey):
                # In production the SigningKeyService might be remote; for the
                # POC the local-Ed25519 adapter is the primary path.
                raise SigningError(
                    "Only LocalEd25519SigningKey is wired into the POC signer."
                )

            return jwt.encode(
                payload.model_dump(),
                self._signing.private_pem(),
                algorithm="EdDSA",
                headers={"alg": "EdDSA", "typ": "JWT", "kid": kid},
            )
        except SigningError:
            raise
        except Exception as exc:
            raise SigningError(f"Failed to sign contract: {exc}") from exc

    def _self_verify(self, token: str) -> None:
        try:
            jwt.decode(
                token,
                self._signing.public_pem(),
                algorithms=["EdDSA"],
                audience=self._node_id,
            )
        except Exception as exc:
            raise SelfVerificationError(
                f"Self-verification failed for freshly minted token: {exc}"
            ) from exc
