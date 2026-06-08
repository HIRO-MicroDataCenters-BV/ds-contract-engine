"""Validation endpoint — POST /v1/validate."""

import logging

from classy_fastapi import Routable, post
from fastapi import Depends, HTTPException

from app.core.usecases import ValidateContractUsecase
from app.rest_api.depends import get_validate_contract_usecase
from app.rest_api.serializers import ValidateRequest, ValidateResponse
from app.rest_api.tags import VALIDATION

logger = logging.getLogger("ds_contract_validator.routes.validate")


class ValidateRoutes(Routable):
    @post(
        "/v1/validate",
        operation_id="validate_contract",
        summary="Validate a contract token",
        response_model=ValidateResponse,
        tags=[VALIDATION],
    )
    async def validate_contract(
        self,
        body: ValidateRequest,
        usecase: ValidateContractUsecase = Depends(get_validate_contract_usecase),
    ) -> ValidateResponse:
        """Validates a VC-JWT contract.

        Returns `{allow, reason, jti, order_id}`. The Connector Service uses
        the `allow` flag to decide whether to fetch node-local data.
        """
        try:
            result = await usecase.execute(body.token)
        except Exception as exc:
            logger.exception("Unexpected validation failure")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return ValidateResponse(
            allow=result.allow,
            reason=result.reason,
            jti=result.jti,
            order_id=result.order_id,
        )


routes = ValidateRoutes()
