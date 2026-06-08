"""Contract registration + status endpoints — the stub's whole API surface."""

import logging

from classy_fastapi import Routable, get, patch, post
from fastapi import HTTPException

from app.rest_api.serializers import (
    ContractRecord,
    RegisterContractRequest,
    UpdateStatusRequest,
)
from app.storage import ContractStore

logger = logging.getLogger("ds_clearing_house_stub.routes")

# Single shared store — module-level for simplicity in the stub.
store = ContractStore()


class ContractsRoutes(Routable):
    @post(
        "/v1/contracts",
        operation_id="register_contract",
        summary="Register a freshly minted contract",
        response_model=ContractRecord,
        status_code=201,
        tags=["Contracts"],
    )
    async def register(self, body: RegisterContractRequest) -> ContractRecord:
        record = store.register(
            jti=body.jti,
            order_id=body.order_id,
            consumer_id=body.consumer_id,
            iat=body.iat,
            exp=body.exp,
        )
        return ContractRecord(**record)

    @get(
        "/v1/contracts/{jti}",
        operation_id="get_contract",
        summary="Read a contract's current status",
        response_model=ContractRecord,
        tags=["Contracts"],
    )
    async def get_contract(self, jti: str) -> ContractRecord:
        record = store.get(jti)
        if record is None:
            raise HTTPException(status_code=404, detail=f"jti '{jti}' not registered")
        return ContractRecord(**record)

    @get(
        "/v1/contracts",
        operation_id="list_contracts",
        summary="List all registered contracts (debug)",
        response_model=list[ContractRecord],
        tags=["Contracts"],
    )
    async def list_contracts(self) -> list[ContractRecord]:
        return [ContractRecord(**r) for r in store.list_all()]

    @patch(
        "/v1/contracts/{jti}/status",
        operation_id="update_contract_status",
        summary="Manually change a contract's status (for testing revocation)",
        response_model=ContractRecord,
        tags=["Contracts"],
    )
    async def update_status(
        self, jti: str, body: UpdateStatusRequest
    ) -> ContractRecord:
        record = store.update_status(jti, body.status)
        if record is None:
            raise HTTPException(status_code=404, detail=f"jti '{jti}' not registered")
        return ContractRecord(**record)


routes = ContractsRoutes()
