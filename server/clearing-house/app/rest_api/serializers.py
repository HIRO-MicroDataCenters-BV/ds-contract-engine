"""HTTP-facing schemas for the Clearing House."""

from pydantic import BaseModel


class HealthCheck(BaseModel):
    status: str = "OK"
