"""HTTP-facing Pydantic schemas for the Contract Generator REST API."""

from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.entities import CatalogItem


class HealthCheck(BaseModel):
    status: str = "OK"


class GenerateContractRequest(BaseModel):
    """Body for POST /v1/contracts.

    Matches the Checkout → Generator contract documented in
    docs/contract-engine-payload-spec.md §9.1.
    """

    consumer_id: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1)
    ttl_seconds: Optional[int] = Field(default=None, ge=1)
    items: List[CatalogItem] = Field(..., min_length=1)


class GenerateContractResponse(BaseModel):
    """Response body returned to Checkout."""

    token: str
    jti: str
    exp: int


class JWKSet(BaseModel):
    keys: List[dict]
