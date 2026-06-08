"""Settings for the Contract Validator — DS__-prefixed env vars."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_prefix="DS__",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Node identity ----------------------------------------------------
    node_id: str = "localhost"

    # --- Upstream services -----------------------------------------------
    # Clearing House for the local node — used to look up jti status.
    clearing_house_url: str = "http://localhost:9001"

    # JWKS base URL template. The Validator constructs the full URL by joining
    # this with the issuing node's identity from the token's iss claim.
    # For the simple case where every node hosts JWKS at https://<iss>/.well-known/jwks.json
    # leave this empty and the Validator derives the URL from iss directly.
    jwks_base_url_template: str = ""

    # --- Behaviour --------------------------------------------------------
    leeway_seconds: int = 5  # clock skew tolerance for iat / exp
    jwks_cache_ttl_seconds: int = 3600
    http_timeout_seconds: float = 5.0

    # --- Server -----------------------------------------------------------
    port: int = 8083
    host: str = "0.0.0.0"
    log_level: str = "INFO"
    environment: str = "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
