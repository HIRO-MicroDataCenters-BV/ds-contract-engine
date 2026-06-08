"""JWKS endpoint — publishes this node's active public key for Validators."""

from classy_fastapi import Routable, get
from fastapi import Depends

from app.adapters.signing_key_service import LocalEd25519SigningKey
from app.rest_api.depends import get_signing_key_service
from app.rest_api.serializers import JWKSet
from app.rest_api.tags import JWKS


class JWKSRoutes(Routable):
    @get(
        "/.well-known/jwks.json",
        operation_id="get_jwks",
        summary="Public key set (JWKS) for this node",
        response_model=JWKSet,
        tags=[JWKS],
    )
    async def get_jwks(
        self,
        signing: LocalEd25519SigningKey = Depends(get_signing_key_service),
    ) -> JWKSet:
        """Returns the active public key in JWK form so Validators on other
        nodes can verify tokens minted here."""
        return JWKSet(keys=[signing.public_jwk()])


routes = JWKSRoutes()
