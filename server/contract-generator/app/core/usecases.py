"""Contract generation use-case.

Pure orchestration. Accepts a request, validates that each item belongs
to this node, projects each item through the configured catalog-field
schema, builds the payload, signs, self-verifies, registers with the
Clearing House, returns the token. No HTTP concerns leak in.
"""

import logging
import time
import uuid
from typing import Tuple
from urllib.parse import urlparse

import jwt

from app.core.catalog_fields import CatalogFieldSchema
from app.core.entities import (
    ContractGenerationRequest,
    ContractPayload,
    CredentialSubject,
    VerifiableCredential,
)
from app.core.exceptions import (
    MissingFieldError,
    SelfVerificationError,
    SigningError,
    TooManyItemsError,
    WrongNodeError,
)
from app.core.ports import ClearingHouse, SigningKeyService

logger = logging.getLogger("ds_contract_generator.usecases")


class GenerateContractUsecase:
    def __init__(
        self,
        node_id: str,
        signing_key_service: SigningKeyService,
        clearing_house: ClearingHouse,
        catalog_field_schema: CatalogFieldSchema,
        default_ttl_seconds: int = 3600,
        max_items_per_contract: int = 50,
    ) -> None:
        self._node_id = node_id
        self._signing = signing_key_service
        self._ch = clearing_house
        self._schema = catalog_field_schema
        self._default_ttl = default_ttl_seconds
        self._max_items = max_items_per_contract

    async def execute(self, request: ContractGenerationRequest) -> Tuple[str, str, int]:
        """Mint a contract.

        Returns: (token, jti, exp)
        """
        # 1. Bound the request size.
        if len(request.items) > self._max_items:
            raise TooManyItemsError(
                f"Request bundles {len(request.items)} items "
                f"(max {self._max_items})."
            )

        # 2. Node-ownership check: every item's @id host must equal this node.
        self._verify_node_ownership(request)

        # 3. Project each item through the configured field schema.
        projected_items = self._project_items(request)

        # 4. Assemble payload.
        now = int(time.time())
        ttl = (
            request.ttl_seconds
            if request.ttl_seconds is not None
            else self._default_ttl
        )
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
                credentialSubject=CredentialSubject(catalogItem=projected_items)
            ),
        )

        # 5. Sign.
        token = self._sign(payload)

        # 6. Primary verification — never ship a corrupted token.
        self._self_verify(token, payload)

        # 7. Register with the local Clearing House.
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

    def _verify_node_ownership(self, request: ContractGenerationRequest) -> None:
        """Reject mints for items that don't belong to this node.

        Each catalog item's `id` is its DCAT-AP `@id` URI; the URI's host
        identifies the owning node. This Generator only signs for its
        own node's items.
        """
        for item in request.items:
            host = urlparse(item.id).hostname
            if host is None:
                # Non-URI ids are allowed only if they start with the node id.
                if not item.id.startswith(self._node_id):
                    logger.warning(
                        "contract.refused.cross_node "
                        "consumer=%s order_id=%s item_id=%r reason=no_host",
                        request.consumer_id,
                        request.order_id,
                        item.id,
                    )
                    raise WrongNodeError(
                        f"item id {item.id!r} has no host and does not start "
                        f"with node id {self._node_id!r}"
                    )
            elif host != self._node_id:
                logger.warning(
                    "contract.refused.cross_node "
                    "consumer=%s order_id=%s item_id=%r item_host=%s "
                    "this_node=%s",
                    request.consumer_id,
                    request.order_id,
                    item.id,
                    host,
                    self._node_id,
                )
                raise WrongNodeError(
                    f"item {item.id!r} host {host!r} does not match "
                    f"node {self._node_id!r}"
                )

    def _project_items(self, request: ContractGenerationRequest) -> list[dict]:
        """Apply the configured field schema to each incoming item."""
        out: list[dict] = []
        for item in request.items:
            item_dict = item.model_dump()
            try:
                out.append(self._schema.project(item_dict))
            except KeyError as exc:
                raise MissingFieldError(str(exc)) from exc
        return out

    def _sign(self, payload: ContractPayload) -> str:
        try:
            from app.adapters.signing_key_service import LocalEd25519SigningKey

            if not isinstance(self._signing, LocalEd25519SigningKey):
                raise SigningError(
                    "Only LocalEd25519SigningKey is wired into the POC signer."
                )

            return jwt.encode(
                payload.model_dump(),
                self._signing.private_pem(),
                algorithm="EdDSA",
                headers={"alg": "EdDSA", "typ": "JWT", "kid": self._signing.kid()},
            )
        except SigningError:
            raise
        except Exception as exc:
            raise SigningError(f"Failed to sign contract: {exc}") from exc

    def _self_verify(self, token: str, expected: ContractPayload) -> None:
        """Decode the freshly minted token and compare against expectations.

        Catches:
          - signature broken (wrong key, tampered payload)
          - aud / exp wrong
          - header kid not the active one
          - decoded payload doesn't match Pydantic shape
          - critical claims don't round-trip (jti, order_id, iss, aud, sub)
        """
        # Header check first — cheap and locates kid mismatches early.
        try:
            header = jwt.get_unverified_header(token)
        except Exception as exc:
            raise SelfVerificationError(f"unreadable header: {exc}") from exc

        if header.get("kid") != self._signing.kid():
            raise SelfVerificationError(
                f"header kid {header.get('kid')!r} != active kid "
                f"{self._signing.kid()!r}"
            )

        # Full signature + claims verification.
        try:
            decoded = jwt.decode(
                token,
                self._signing.public_pem(),
                algorithms=["EdDSA"],
                audience=self._node_id,
            )
        except Exception as exc:
            raise SelfVerificationError(
                f"signature verification failed: {exc}"
            ) from exc

        # Schema round-trip — catches Pydantic-level corruption.
        try:
            recovered = ContractPayload.model_validate(decoded)
        except Exception as exc:
            raise SelfVerificationError(
                f"decoded payload schema invalid: {exc}"
            ) from exc

        # Critical claims must round-trip exactly.
        for field in ("jti", "order_id", "iss", "aud", "sub"):
            got = getattr(recovered, field)
            want = getattr(expected, field)
            if got != want:
                raise SelfVerificationError(
                    f"{field} round-trip mismatch: got {got!r}, expected {want!r}"
                )
