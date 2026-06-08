"""HTTP schemas for the stub Clearing House."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthCheck(BaseModel):
    status: str = "OK"


class RegisterContractRequest(BaseModel):
    jti: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1)
    status: Literal["active"] = "active"
    consumer_id: str = Field(..., min_length=1)
    iat: int
    exp: int


class ContractRecord(BaseModel):
    jti: str
    order_id: str
    status: str
    consumer_id: str
    iat: int
    exp: int


class UpdateStatusRequest(BaseModel):
    status: Literal["active", "completed", "cancelled", "revoked"]
