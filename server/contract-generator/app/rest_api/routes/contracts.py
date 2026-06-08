"""Contract minting endpoint — POST /v1/contracts."""

import logging

from classy_fastapi import Routable, post
from fastapi import Depends, HTTPException

from app.core.entities import ContractGenerationRequest
from app.core.exceptions import (
    ClearingHouseError,
    SelfVerificationError,
    SigningError,
    TooManyItemsError,
)
from app.core.usecases import GenerateContractUsecase
from app.rest_api.depends import get_generate_contract_usecase
from app.rest_api.serializers import (
    GenerateContractRequest,
    GenerateContractResponse,
)
from app.rest_api.tags import CONTRACTS

logger = logging.getLogger("ds_contract_generator.routes.contracts")


class ContractsRoutes(Routable):
    @post(
        "/v1/contracts",
        operation_id="generate_contract",
        summary="Mint a new contract",
        response_model=GenerateContractResponse,
        tags=[CONTRACTS],
    )
    async def generate_contract(
        self,
        body: GenerateContractRequest,
        usecase: GenerateContractUsecase = Depends(get_generate_contract_usecase),
    ) -> GenerateContractResponse:
        """Mints a signed VC-JWT covering all of this node's selected items.

        Called by the Checkout Service after it has grouped catalog items by
        owning node and identified this node as the owner of the items in the
        request body.
        """
        try:
            domain_request = ContractGenerationRequest(
                consumer_id=body.consumer_id,
                order_id=body.order_id,
                ttl_seconds=body.ttl_seconds,
                items=body.items,
            )
            token, jti, exp = await usecase.execute(domain_request)
            return GenerateContractResponse(token=token, jti=jti, exp=exp)
        except TooManyItemsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SigningError as exc:
            logger.exception("Signing failed")
            raise HTTPException(status_code=500, detail="Signing failed") from exc
        except SelfVerificationError as exc:
            logger.exception("Self-verification failed")
            raise HTTPException(
                status_code=500, detail="Self-verification failed"
            ) from exc
        except ClearingHouseError as exc:
            logger.exception("Clearing House registration failed")
            raise HTTPException(
                status_code=502, detail="Clearing House unavailable"
            ) from exc


routes = ContractsRoutes()
