"""Settings — bound to environment variables with prefix DS__.

Mirrors the pattern used in ds-catalog (env_prefix="DS__", env_nested_delimiter="__").
"""

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
    # The provider node this Generator runs on. Used as iss, aud, and JWKS host.
    node_id: str = "localhost"

    # --- Signing key ------------------------------------------------------
    # Path to PEM-encoded Ed25519 private key. If the file does not exist on
    # startup, a fresh keypair is generated and persisted at this path
    # (development convenience — production deployments mount a Secret).
    signing_key_path: str = "./local-ed25519.pem"
    # Stable kid published in the JWT header and JWKS endpoint.
    signing_key_id: str = "localhost#key-1"

    # --- Upstream services -----------------------------------------------
    # Local Clearing House for jti registration.
    clearing_house_url: str = "http://localhost:9001"

    # --- Token defaults ---------------------------------------------------
    default_ttl_seconds: int = 3600
    max_items_per_contract: int = 50

    # --- Server -----------------------------------------------------------
    port: int = 8082
    host: str = "0.0.0.0"
    log_level: str = "INFO"
    environment: str = "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
