"""HTTP request and response models.

Named api_models, not models, to keep them distinct from app/core/models,
which describes the database tables. The two are separate on purpose: They
describe the same things but change for different reasons: adding an internal
column should not silently reshape the public API.

The request shapes are fixed by the two callers, which are already written
against the stub this service replaces — see clearing-house-stub. Changing
them is not a local decision.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthCheck(BaseModel):
    status: str = "OK"


class RegisterContractRequest(BaseModel):
    """Body of POST /v1/contracts, as the Contract Generator sends it."""

    # min_length guards against an empty id, which would create a row nothing
    # could ever look up.
    jti: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1)

    # Accepted because the Generator sends it, then ignored: every contract
    # starts active, and one arriving already revoked would be meaningless.
    # Kept as Literal["active"] so anything else is a 422 rather than a
    # silently discarded value.
    status: Literal["active"] = "active"

    consumer_id: str = Field(..., min_length=1)
    iat: int
    exp: int


class UpdateStatusRequest(BaseModel):
    """Body of PATCH /v1/contracts/{jti}/status.

    All four statuses are accepted here. Whether a particular change is
    permitted is the state machine's decision, not Pydantic's — so
    revoked -> active passes validation and is then refused with 409, which
    is the right distinction: the request is well formed, it conflicts.
    """

    status: Literal["active", "completed", "cancelled", "revoked"]


class ContractRecord(BaseModel):
    """A contract, as returned to callers.

    The stub returns the first six fields. The last two are additional: both
    callers ignore fields they do not recognise, so this is a safe superset,
    and status_changed_at answers "when was this revoked?" without a second
    request.
    """

    # from_attributes lets model_validate() read straight off an ORM object,
    # so routes do not hand-copy eight fields.
    model_config = ConfigDict(from_attributes=True)

    jti: str
    order_id: str
    status: str
    consumer_id: str
    iat: int
    exp: int
    registered_at: int
    status_changed_at: int
