"""FastAPI dependency wiring.

Builds the chain routes need:

    get_database()  ->  get_repository()  ->  get_usecase()

Two reasons this is not inlined into the routes. It is the single place the
concrete implementation is named, so swapping SqlRepository for another one
touches nothing else. And every link is an override point: a test can replace
any of them with a fake and exercise routes without a database.

Following ds-checkout, get_usecase lives in each route module rather than
here, so overriding it in one route's tests cannot affect another's.
"""

from fastapi import Depends

from app.core.repository import Repositories, SqlRepository
from app.database import Database, get_database


def get_repository(database: Database = Depends(get_database)) -> Repositories:
    """The storage implementation. The only place it is chosen."""
    return SqlRepository(database)
