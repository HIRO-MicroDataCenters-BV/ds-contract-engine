"""FastAPI entry point for ds-clearing-house."""

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from prometheus_fastapi_instrumentator import Instrumentator

from app import __version__
from app.database import init_database
from app.rest_api.routes import contracts, health_check
from app.settings import get_settings

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("ds_clearing_house")


class CustomFastAPI(FastAPI):
    def openapi(self) -> Dict[str, Any]:
        if self.openapi_schema:
            return self.openapi_schema
        schema = get_openapi(
            title="Data Space — Clearing House",
            version=__version__,
            description=(
                "Per-node contract registry and tamper-evident audit ledger. "
                "The Contract Generator registers newly minted contracts here; "
                "the Contract Validator reads their status on every data "
                "access. Sub-service of the Contract Engine."
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


database = init_database(settings.database.url, echo=settings.database.echo)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Open the database on startup, close it on shutdown.

    Deliberately does not create tables — schema comes from migrations, in
    every environment, so development and production follow the same path.
    Run `alembic upgrade head` before starting.
    """
    await database.connect()
    yield
    await database.close()


# redirect_slashes=False is deliberate and load-bearing.
#
# With the default (True), `GET /v1/contracts/` 307-redirects. The Validator's
# httpx client does not follow redirects and treats any >= 300 as a failure;
# worse, were it to follow one to a list endpoint, it would call
# `body.get("status")` on a JSON array and raise AttributeError outside its
# fail-closed path — turning a graceful deny into an HTTP 500.
app = CustomFastAPI(redirect_slashes=False, lifespan=lifespan)

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

logger.info(
    "ds-clearing-house started node_id=%s environment=%s",
    settings.node_id,
    settings.environment,
)
