"""FastAPI entry point for ds-contract-validator."""

import logging
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from prometheus_fastapi_instrumentator import Instrumentator

from app import __version__
from app.rest_api.routes import health_check, validate
from app.settings import get_settings

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("ds_contract_validator")


class CustomFastAPI(FastAPI):
    def openapi(self) -> Dict[str, Any]:
        if self.openapi_schema:
            return self.openapi_schema
        schema = get_openapi(
            title="Data Space — Contract Validator",
            version=__version__,
            description=(
                "Validates VC-JWT contracts before the Connector Service "
                "fetches node-local data. Sub-service of the Contract Engine "
                "(DS-307)."
            ),
            contact={
                "name": "HIRO-MicroDataCenters",
                "email": "all-hiro@hiro-microdatacenters.nl",
            },
            license_info={
                "name": "MIT",
                "url": "https://github.com/HIRO-MicroDataCenters-BV"
                "/ds-contract-engine/blob/main/LICENSE",
            },
            routes=self.routes,
        )
        self.openapi_schema = schema
        return self.openapi_schema


app = CustomFastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)

app.include_router(health_check.routes.router)
app.include_router(validate.routes.router)

logger.info(
    "ds-contract-validator started node_id=%s leeway=%ss",
    settings.node_id,
    settings.leeway_seconds,
)
