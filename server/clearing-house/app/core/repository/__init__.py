"""Storage.

    from app.core.repository import Repositories, SqlRepository

Repositories is the interface — what storage must be able to do.
SqlRepository is the implementation used in every environment today.
"""

from app.core.repository.repositories import (
    CONTRACT_SORT_COLUMNS,
    EVENT_REGISTERED,
    EVENT_STATUS_CHANGED,
    SORT_EXP,
    SORT_REGISTERED_AT,
    ContractQuery,
    ContractSort,
    EventQuery,
    Repositories,
)
from app.core.repository.sql_repository import SqlRepository

__all__ = [
    "CONTRACT_SORT_COLUMNS",
    "EVENT_REGISTERED",
    "EVENT_STATUS_CHANGED",
    "SORT_EXP",
    "SORT_REGISTERED_AT",
    "ContractQuery",
    "ContractSort",
    "EventQuery",
    "Repositories",
    "SqlRepository",
]
