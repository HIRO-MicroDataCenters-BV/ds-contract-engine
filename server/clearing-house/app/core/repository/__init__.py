"""Storage.

    from app.core.repository import Repositories, SqlRepository

Repositories is the interface — what storage must be able to do.
SqlRepository is the implementation used in every environment today.
"""

from app.core.repository.repositories import (
    EVENT_REGISTERED,
    EVENT_STATUS_CHANGED,
    Repositories,
)
from app.core.repository.sql_repository import SqlRepository

__all__ = [
    "EVENT_REGISTERED",
    "EVENT_STATUS_CHANGED",
    "Repositories",
    "SqlRepository",
]
