"""Domain entities for the Validator. Mirrors the Generator's payload model."""

from typing import List, Optional

from pydantic import BaseModel, Field


class CatalogItem(BaseModel):
    id: str
    identifier: str
    title: str
    hash: str = Field(pattern=r"^sha256:[0-9a-f]{32,64}$")


class CredentialSubject(BaseModel):
    catalogItem: List[CatalogItem]


class VerifiableCredential(BaseModel):
    type: List[str]
    credentialSubject: CredentialSubject


class ContractPayload(BaseModel):
    jti: str
    iss: str
    aud: str
    sub: str
    iat: int
    exp: int
    order_id: str
    vc: VerifiableCredential


class ValidationResult(BaseModel):
    """Outcome of a single validation call."""

    allow: bool
    reason: Optional[str] = None
    jti: Optional[str] = None
    order_id: Optional[str] = None
