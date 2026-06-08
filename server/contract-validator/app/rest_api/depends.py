"""Dependency wiring for the Validator."""

from functools import lru_cache

from app.adapters.clearing_house import HttpClearingHouseReader
from app.adapters.jwks_resolver import HttpJWKSResolver
from app.core.usecases import ValidateContractUsecase
from app.settings import get_settings


@lru_cache(maxsize=1)
def get_jwks_resolver() -> HttpJWKSResolver:
    s = get_settings()
    return HttpJWKSResolver(
        cache_ttl_seconds=s.jwks_cache_ttl_seconds,
        timeout_seconds=s.http_timeout_seconds,
        base_url_template=s.jwks_base_url_template,
    )


@lru_cache(maxsize=1)
def get_clearing_house() -> HttpClearingHouseReader:
    s = get_settings()
    return HttpClearingHouseReader(
        base_url=s.clearing_house_url,
        timeout_seconds=s.http_timeout_seconds,
    )


def get_validate_contract_usecase() -> ValidateContractUsecase:
    s = get_settings()
    return ValidateContractUsecase(
        node_id=s.node_id,
        jwks_resolver=get_jwks_resolver(),
        clearing_house=get_clearing_house(),
        leeway_seconds=s.leeway_seconds,
    )
