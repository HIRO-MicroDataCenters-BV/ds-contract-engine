from classy_fastapi import Routable, get

from app.rest_api.serializers import HealthCheck


class HealthCheckRoutes(Routable):
    @get(
        "/health-check/",
        operation_id="health_check",
        summary="Health check",
        response_model=HealthCheck,
        tags=["Health"],
    )
    async def health_check(self) -> dict[str, str]:
        return {"status": "OK"}


routes = HealthCheckRoutes()
