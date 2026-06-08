"""FastAPI entry point for the stub Clearing House."""

import logging
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from prometheus_fastapi_instrumentator import Instrumentator

from app import __version__
from app.rest_api.routes import contracts, health_check
from app.settings import get_settings

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("ds_clearing_house_stub")


class CustomFastAPI(FastAPI):
    def openapi(self) -> Dict[str, Any]:
        if self.openapi_schema:
            return self.openapi_schema
        schema = get_openapi(
            title="Data Space — Clearing House (stub)",
            version=__version__,
            description=(
                "In-memory Clearing House stub for Contract Engine end-to-end "
                "testing. Not the real Clearing House."
            ),
            contact={
                "name": "HIRO-MicroDataCenters",
                "email": "all-hiro@hiro-microdatacenters.nl",
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
app.include_router(contracts.routes.router)

logger.info("ds-clearing-house-stub started port=%s", settings.port)
