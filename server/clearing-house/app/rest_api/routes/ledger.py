"""The ledger feed: history across every contract.

Added for the admin console. Nothing in the contract flow calls it — the
Generator and Validator only ever touch /v1/contracts.
"""

import logging
from typing import Literal, Optional

from classy_fastapi import Routable, get
from fastapi import Depends, HTTPException, Query, status

from app.core.repository import Repositories
from app.core.usecases import ContractUsecases
from app.rest_api.api_models import AuditEventPage, AuditEventRecord
from app.rest_api.depends import get_repository
from app.rest_api.pagination import page_count
from app.rest_api.tags import LEDGER

logger = logging.getLogger(__name__)

Status = Literal["active", "completed", "cancelled", "revoked"]


def get_usecase(
    repository: Repositories = Depends(get_repository),
) -> ContractUsecases:
    """Defined per route module, as in contracts.py, so overriding it in one
    module's tests cannot affect another's."""
    return ContractUsecases(repository)


class LedgerRoutes(Routable):
    @get(
        "/v1/audit/events",
        operation_id="list_audit_events",
        summary="The history log across every contract, newest first",
        response_model=AuditEventPage,
        tags=[LEDGER],
    )
    async def list_audit_events(
        self,
        event_type: Optional[str] = Query(
            None,
            min_length=1,
            description="e.g. contract.status_change_rejected",
        ),
        jti: Optional[str] = Query(None, min_length=1),
        order_id: Optional[str] = Query(None, min_length=1),
        consumer_id: Optional[str] = Query(None, min_length=1),
        from_status: Optional[Status] = Query(None),
        to_status: Optional[Status] = Query(None),
        since: Optional[int] = Query(
            None, ge=0, description="Unix seconds, inclusive."
        ),
        until: Optional[int] = Query(
            None, ge=0, description="Unix seconds, exclusive."
        ),
        page: int = Query(1, ge=1, description="Pages count from 1."),
        limit: int = Query(50, ge=1, le=200),
        usecases: ContractUsecases = Depends(get_usecase),
    ) -> AuditEventPage:
        """Every recorded event, including refused attempts.

        The query an operator most needs is
        `?event_type=contract.status_change_rejected&to_status=active` —
        everyone who tried to bring a finished contract back.

        `event_type` is free text rather than an enum on purpose: new kinds of
        event are planned, and an enum would make each one a breaking API
        change. An unknown type simply matches nothing.

        The window is half-open, [since, until). Viewing 09:00–10:00 and then
        10:00–11:00 therefore shows an event at exactly 10:00 once, not twice.
        """
        if since is not None and until is not None and since > until:
            # Always a caller mistake. Returning an empty page would hide it;
            # an empty page is reserved for a window that is genuinely empty,
            # which since == until is.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"since ({since}) is after until ({until})",
            )

        listing = await usecases.list_events(
            page=page,
            limit=limit,
            event_type=event_type,
            jti=jti,
            order_id=order_id,
            consumer_id=consumer_id,
            from_status=from_status,
            to_status=to_status,
            occurred_at_or_after=since,
            occurred_before=until,
        )
        return AuditEventPage(
            items=[AuditEventRecord.model_validate(e) for e in listing.items],
            page=page,
            limit=limit,
            total=listing.total,
            total_pages=page_count(listing.total, limit),
        )


routes = LedgerRoutes()
