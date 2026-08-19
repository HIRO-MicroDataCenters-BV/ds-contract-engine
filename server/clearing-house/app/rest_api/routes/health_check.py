"""Health probe.

Deliberately does not touch storage. With replicaCount 1 there is nowhere to
fail over to, so a database blip failing readiness would turn a hiccup into
mint failures, and a failing liveness probe would restart the only pod. A
deep check belongs on a separate, unwired endpoint.
"""

from classy_fastapi import Routable, get

from app.rest_api.serializers import HealthCheck
from app.rest_api.tags import HEALTH


class HealthCheckRoutes(Routable):
    @get(
        "/health-check/",
        operation_id="health_check",
        summary="Health check",
        response_model=HealthCheck,
        tags=[HEALTH],
    )
    async def health_check(self) -> dict[str, str]:
        return {"status": "OK"}


routes = HealthCheckRoutes()
