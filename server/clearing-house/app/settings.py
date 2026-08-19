"""Settings for the Clearing House — DS__-prefixed env vars."""

from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    """Storage configuration. Env vars: DS__DATABASE__URL, DS__DATABASE__ECHO."""

    # Note the slash count when moving to a container: three slashes is a
    # RELATIVE path, so sqlite+aiosqlite:///ch.db lands in the working
    # directory and is lost on restart. The absolute form used in Kubernetes
    # is sqlite+aiosqlite:////data/ch.db — four.
    url: str = "sqlite+aiosqlite:///./clearing_house.db"

    # Log every SQL statement. Noisy; useful when a query misbehaves.
    echo: bool = False


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
    # Stamped onto every ledger entry. Never taken from a request body — a
    # writer must not be able to attribute events to another node.
    node_id: str = "localhost"

    # --- Storage ----------------------------------------------------------
    database: DatabaseSettings = DatabaseSettings()

    # --- Server -----------------------------------------------------------
    port: int = 8080
    host: str = "0.0.0.0"
    log_level: str = "INFO"
    environment: str = "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
