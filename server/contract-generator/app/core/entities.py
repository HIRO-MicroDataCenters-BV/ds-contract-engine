"""Domain entities — VC-JWT v1 payload models.

Locked v1 payload as documented in docs/payload-format.md.

`CatalogItem` allows extra fields (`extra="allow"`) so the dynamic
field schema in catalog_fields.yaml can pull in additional attributes
beyond the v1 four. When the consortium agrees to include `license`,
`format`, etc., Checkout starts sending them and Pydantic accepts
them without a model change.

`CredentialSubject.catalogItem` is a list of dicts (not strict
CatalogItem instances) because the Generator projects each item
through the field schema before embedding — the exact shape in the
token is config-driven.
"""

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CatalogItem(BaseModel):
    """A single catalog item received from Checkout.

    The four named attributes are the locked v1 set. Additional fields
    are accepted so the catalog-field schema (catalog_fields.yaml) can
    surface them in the token without a code change.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    identifier: str
    title: str
    hash: str = Field(pattern=r"^sha256:[0-9a-f]{32,64}$")


class CredentialSubject(BaseModel):
    """The body of the VC-JWT — kept lean. Identifiers come from outer JWT claims."""

    catalogItem: List[dict[str, Any]]


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
