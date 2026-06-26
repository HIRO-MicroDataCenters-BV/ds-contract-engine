"""HTTP-facing Pydantic schemas for the Contract Generator REST API.

Each model carries a Swagger example payload that uses ``localhost`` as the
item host, matching the default NODE_ID. Override these in production
deployments where NODE_ID is a real node hostname.
"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

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

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "consumer_id": "researcher-sai-kireeti",
                    "order_id": "9d8e7c6b-5a4f-3e2d-1c0b-a9f8e7d6c5b4",
                    "ttl_seconds": 3600,
                    "items": [
                        {
                            "id": "http://localhost/dataset-test-2907",
                            "identifier": "synthetic_dataset_test_2907",
                            "title": "GWAS on Cats 2907",
                            "hash": (
                                "sha256:3a7bd3e2360a3b5c1b2ef3b1a4e8f7a6"
                                "00000000000000000000000000000000"
                            ),
                        }
                    ],
                }
            ]
        }
    )


class GenerateContractResponse(BaseModel):
    """Response body returned to Checkout."""

    token: str
    jti: str
    exp: int


class JWKSet(BaseModel):
    keys: List[dict]
