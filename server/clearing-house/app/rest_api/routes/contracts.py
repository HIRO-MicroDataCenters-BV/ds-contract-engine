"""The three contract endpoints.

Every status code here is fixed by the two callers, which are already written
against the stub this service replaces. They are not local design decisions —
see clearing-house-stub and the adapters in contract-generator and
contract-validator.
"""

import logging

from classy_fastapi import Routable, get, patch, post
from fastapi import Depends, HTTPException, status

from app.core.exceptions import IllegalStatusTransition
from app.core.repository import Repositories
from app.core.usecases import ContractUsecases
from app.rest_api.depends import get_repository
from app.rest_api.api_models import (
    ContractRecord,
    RegisterContractRequest,
    UpdateStatusRequest,
)
from app.rest_api.tags import CONTRACTS

logger = logging.getLogger(__name__)


def get_usecase(
    repository: Repositories = Depends(get_repository),
) -> ContractUsecases:
    """Defined per route module, following ds-checkout, so overriding it in
    one route's tests cannot affect another's."""
    return ContractUsecases(repository)


class ContractsRoutes(Routable):
    @post(
        "/v1/contracts",
        operation_id="register_contract",
        summary="Register a freshly minted contract",
        response_model=ContractRecord,
        status_code=status.HTTP_201_CREATED,
        tags=[CONTRACTS],
    )
    async def register_contract(
        self,
        body: RegisterContractRequest,
        usecases: ContractUsecases = Depends(get_usecase),
    ) -> ContractRecord:
        """Record a contract the Generator has just signed.

        Idempotent: the Generator makes one attempt with no retry budget, so
        registering the same jti twice returns the existing contract rather
        than failing.

        `body.status` is deliberately not passed on. Every contract starts
        active; one arriving already revoked would be meaningless.
        """
        contract = await usecases.register(
            jti=body.jti,
            order_id=body.order_id,
            consumer_id=body.consumer_id,
            iat=body.iat,
            exp=body.exp,
        )
        return ContractRecord.model_validate(contract)

    @get(
        "/v1/contracts/{jti}",
        operation_id="get_contract",
        summary="Read a contract's current status",
        response_model=ContractRecord,
        tags=[CONTRACTS],
    )
    async def get_contract(
        self,
        jti: str,
        usecases: ContractUsecases = Depends(get_usecase),
    ) -> ContractRecord:
        """The hot path: read by the Validator on every data access.

        The 404 below is load-bearing. The Validator's adapter maps it to the
        string "not_registered" and denies gracefully; a 500, or a 200 with an
        unexpected body, escapes its fail-closed path entirely. The detail
        wording matches the stub so log greps survive the cutover.
        """
        contract = await usecases.read(jti)
        if contract is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"jti '{jti}' not registered",
            )
        return ContractRecord.model_validate(contract)

    @patch(
        "/v1/contracts/{jti}/status",
        operation_id="update_contract_status",
        summary="Change a contract's status, e.g. revoke it",
        response_model=ContractRecord,
        tags=[CONTRACTS],
    )
    async def update_contract_status(
        self,
        jti: str,
        body: UpdateStatusRequest,
        usecases: ContractUsecases = Depends(get_usecase),
    ) -> ContractRecord:
        """Move a contract to a new status.

        409 when the state machine forbids the change: the request is well
        formed, it conflicts with the contract's current state. The refused
        attempt is recorded in the history before the error is raised.

        Note the ordering — the exception is handled before the None check,
        because an illegal transition on a *known* contract is a conflict,
        not a missing resource.
        """
        try:
            contract = await usecases.change_status(jti, body.status)
        except IllegalStatusTransition as e:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e),
            )

        if contract is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"jti '{jti}' not registered",
            )
        return ContractRecord.model_validate(contract)


routes = ContractsRoutes()
