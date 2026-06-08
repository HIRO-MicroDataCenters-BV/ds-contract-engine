"""Health probe."""

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
