"""The contract endpoints.

The first three are fixed by the two callers, which are already written
against the stub this service replaces. Their status codes are not local
design decisions — see clearing-house-stub and the adapters in
contract-generator and contract-validator.

The list and history endpoints are ours, added for the admin console. Both are about
contracts, so they live here; the global ledger feed gets its own module.
"""

import logging
from typing import Literal, Optional

from classy_fastapi import Routable, get, patch, post
from fastapi import Depends, HTTPException, Query, status

from app.core.exceptions import IllegalStatusTransition
from app.core.repository import Repositories
from app.core.usecases import ContractUsecases
from app.rest_api.depends import get_repository
from app.rest_api.api_models import (
    AuditEventPage,
    AuditEventRecord,
    ContractPage,
    ContractRecord,
    RegisterContractRequest,
    UpdateStatusRequest,
)
from app.rest_api.pagination import InvalidCursor, decode_cursor, encode_cursor
from app.rest_api.tags import CONTRACTS, LEDGER

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
        "/v1/contracts",
        operation_id="list_contracts",
        summary="List contracts, newest first",
        response_model=ContractPage,
        tags=[CONTRACTS],
    )
    async def list_contracts(
        self,
        status_filter: Optional[
            Literal["active", "completed", "cancelled", "revoked"]
        ] = Query(None, alias="status"),
        consumer_id: Optional[str] = Query(None, min_length=1),
        order_id: Optional[str] = Query(None, min_length=1),
        expired: Optional[bool] = Query(
            None,
            description=(
                "true: exp has passed. false: exp is still ahead. Independent "
                "of status — a contract can be active and expired."
            ),
        ),
        limit: int = Query(50, ge=1, le=200),
        cursor: Optional[str] = Query(
            None, description="next_cursor from the previous page. Opaque."
        ),
        usecases: ContractUsecases = Depends(get_usecase),
    ) -> ContractPage:
        """For the admin console. The Generator and Validator never call this.

        Cursor-paged, not offset-paged. New contracts arrive while someone is
        paging, and with offsets each arrival shifts every row down one — so
        page two repeats the end of page one. A cursor names a row, not a
        count, so arrivals cannot move it.

        `status` is exposed under that name but bound to `status_filter`,
        because `status` is already the imported module of HTTP codes that
        the error below depends on.
        """
        try:
            after = decode_cursor(cursor) if cursor is not None else None
        except InvalidCursor as e:
            # 400, not 500: a damaged cursor is the caller's input, and letting
            # it reach the query would surface as a type error.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

        listing = await usecases.list_contracts(
            limit=limit,
            status=status_filter,
            consumer_id=consumer_id,
            order_id=order_id,
            expired=expired,
            after=after,
        )
        return ContractPage(
            items=[ContractRecord.model_validate(c) for c in listing.items],
            next_cursor=(
                encode_cursor(listing.next_position)
                if listing.next_position is not None
                else None
            ),
        )

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

    @get(
        "/v1/contracts/{jti}/history",
        operation_id="get_contract_history",
        summary="The audit trail for one contract",
        response_model=AuditEventPage,
        tags=[LEDGER],
    )
    async def get_contract_history(
        self,
        jti: str,
        usecases: ContractUsecases = Depends(get_usecase),
    ) -> AuditEventPage:
        """Everything recorded against one contract, oldest first.

        Includes refused attempts, which is most of the point: an operator
        wants to see that someone tried three times to reactivate a revoked
        contract, not merely that the contract is revoked.

        404 rather than an empty list when the contract is unknown, matching
        GET /v1/contracts/{jti}. Registration always writes an event, so an
        empty history would mean a bug, never a legitimate answer.
        """
        events = await usecases.history(jti)
        if events is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"jti '{jti}' not registered",
            )
        return AuditEventPage(
            items=[AuditEventRecord.model_validate(e) for e in events]
        )


routes = ContractsRoutes()
