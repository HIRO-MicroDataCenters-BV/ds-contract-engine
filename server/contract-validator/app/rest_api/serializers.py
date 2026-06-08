"""HTTP-facing schemas for the Validator."""

from typing import Optional

from pydantic import BaseModel, Field


class HealthCheck(BaseModel):
    status: str = "OK"


class ValidateRequest(BaseModel):
    token: str = Field(..., min_length=1)


class ValidateResponse(BaseModel):
    allow: bool
    reason: Optional[str] = None
    jti: Optional[str] = None
    order_id: Optional[str] = None
