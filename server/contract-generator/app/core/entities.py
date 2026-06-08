"""Domain entities — VC-JWT v1 payload models.

Locked v1 payload as documented in docs/payload-format.md.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class CatalogItem(BaseModel):
    """A single catalog item granted by a contract.

    `id` is the DCAT-AP @id; `hash` binds the contract to a specific data
    artefact via SHA-256 of the primary distribution.
    """

    id: str
    identifier: str
    title: str
    hash: str = Field(pattern=r"^sha256:[0-9a-f]{32,64}$")


class CredentialSubject(BaseModel):
    """The body of the VC-JWT — kept lean. Identifiers come from outer JWT claims."""

    catalogItem: List[CatalogItem]


class VerifiableCredential(BaseModel):
    type: List[str] = ["NextGenContract"]
    credentialSubject: CredentialSubject


class ContractPayload(BaseModel):
    """The full JWT payload that gets signed into a Contract Engine token."""

    jti: str
    iss: str
    aud: str
    sub: str
    iat: int
    exp: int
    order_id: str
    vc: VerifiableCredential


class ContractGenerationRequest(BaseModel):
    """What Checkout sends to the Generator."""

    consumer_id: str
    order_id: str
    ttl_seconds: Optional[int] = None
    items: List[CatalogItem]
