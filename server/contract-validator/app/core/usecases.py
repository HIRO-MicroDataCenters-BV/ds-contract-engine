"""Validation use-case.

Runs the four checks (signature / aud / exp / registration) and returns a
ValidationResult. Pure orchestration — HTTP concerns live in app/rest_api/.

Catalog hash check is deliberately out of scope for this service in v1 — that
check is performed by the Connector at data-fetch time, since recomputing the
SHA-256 requires reading the actual data which the Validator does not do.
"""

import logging

import jwt

from app.core.entities import ValidationResult
from app.core.exceptions import ClearingHouseError, JWKSError
from app.core.ports import ClearingHouseReader, JWKSResolver

logger = logging.getLogger("ds_contract_validator.usecases")


class ValidateContractUsecase:
    def __init__(
        self,
        node_id: str,
        jwks_resolver: JWKSResolver,
        clearing_house: ClearingHouseReader,
        leeway_seconds: int = 5,
    ) -> None:
        self._node_id = node_id
        self._jwks = jwks_resolver
        self._ch = clearing_house
        self._leeway = leeway_seconds

    async def execute(self, token: str) -> ValidationResult:
        # 1. Decode the unverified header to find kid + iss; we need both before
        #    we can fetch the right public key.
        try:
            header = jwt.get_unverified_header(token)
            unverified = jwt.decode(token, options={"verify_signature": False})
        except Exception as exc:
            return ValidationResult(allow=False, reason=f"malformed token: {exc}")

        kid = header.get("kid")
        iss = unverified.get("iss")
        if not kid or not iss:
            return ValidationResult(allow=False, reason="token missing kid or iss")

        # 2. Fetch the public key from the issuing node's JWKS.
        try:
            public_pem = await self._jwks.get_public_pem(iss=iss, kid=kid)
        except JWKSError as exc:
            return ValidationResult(allow=False, reason=f"JWKS lookup failed: {exc}")

        # 3. Full JWT verification: signature + aud + exp.
        try:
            payload = jwt.decode(
                token,
                public_pem,
                algorithms=["EdDSA"],
                audience=self._node_id,
                leeway=self._leeway,
            )
        except jwt.ExpiredSignatureError:
            logger.warning(
                "contract.refused.expired iss=%s kid=%s this_node=%s",
                iss,
                kid,
                self._node_id,
            )
            return ValidationResult(allow=False, reason="token expired")
        except jwt.InvalidAudienceError:
            # Token signed by some node, intended for another node, presented
            # here. Either a misrouted token (benign bug upstream) or an
            # attempt to use one node's token on another's data. Always log.
            logger.warning(
                "contract.refused.cross_node iss=%s kid=%s this_node=%s "
                "reason=audience_mismatch",
                iss,
                kid,
                self._node_id,
            )
            return ValidationResult(
                allow=False,
                reason=f"token not for this node (aud != {self._node_id})",
            )
        except jwt.InvalidSignatureError:
            logger.warning(
                "contract.refused.bad_signature iss=%s kid=%s this_node=%s",
                iss,
                kid,
                self._node_id,
            )
            return ValidationResult(allow=False, reason="invalid signature")
        except jwt.InvalidTokenError as exc:
            return ValidationResult(allow=False, reason=f"invalid token: {exc}")

        jti = payload.get("jti")
        order_id = payload.get("order_id")
        if not isinstance(jti, str):
            return ValidationResult(allow=False, reason="token missing jti")

        # 4. Registration / revocation check against the local Clearing House.
        try:
            status = await self._ch.get_status(jti)
        except ClearingHouseError as exc:
            return ValidationResult(
                allow=False,
                reason=f"Clearing House unreachable: {exc}",
                jti=jti,
                order_id=order_id,
            )

        if status != "active":
            return ValidationResult(
                allow=False,
                reason=f"contract status is '{status}', not 'active'",
                jti=jti,
                order_id=order_id,
            )

        logger.info("contract.validated.allow jti=%s order_id=%s", jti, order_id)
        return ValidationResult(allow=True, reason=None, jti=jti, order_id=order_id)
