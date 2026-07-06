"""FastAPI dependency providers — wire singletons of adapters and use-cases."""

from functools import lru_cache

from app.adapters.clearing_house import HttpClearingHouse, StubClearingHouse
from app.adapters.signing_key_service import LocalEd25519SigningKey
from app.core.catalog_fields import CatalogFieldSchema
from app.core.usecases import GenerateContractUsecase
from app.settings import Settings, get_settings


@lru_cache(maxsize=1)
def get_catalog_field_schema() -> CatalogFieldSchema:
    """Load the catalog-field schema from the configured YAML path at startup.

    Cached for the lifetime of the process — restart the pod to pick up a
    new schema (e.g. after rolling a ConfigMap).
    """
    s = get_settings()
    return CatalogFieldSchema.load(s.catalog_fields_config_path)


@lru_cache(maxsize=1)
def get_signing_key_service() -> LocalEd25519SigningKey:
    s = get_settings()
    return LocalEd25519SigningKey(
        private_key_path=s.signing_key_path,
        kid=s.signing_key_id,
    )


@lru_cache(maxsize=1)
def get_clearing_house() -> HttpClearingHouse | StubClearingHouse:
    s = get_settings()
    if s.environment == "development" and s.clearing_house_url.startswith(
        "http://localhost"
    ):
        # Convenience: if we're pointing at localhost in development, fall back
        # to the in-memory stub. Production must always use HttpClearingHouse.
        return StubClearingHouse()
    return HttpClearingHouse(base_url=s.clearing_house_url)


def get_generate_contract_usecase() -> GenerateContractUsecase:
    s: Settings = get_settings()
    return GenerateContractUsecase(
        node_id=s.node_id,
        signing_key_service=get_signing_key_service(),
        clearing_house=get_clearing_house(),
        catalog_field_schema=get_catalog_field_schema(),
        default_ttl_seconds=s.default_ttl_seconds,
        max_items_per_contract=s.max_items_per_contract,
    )
