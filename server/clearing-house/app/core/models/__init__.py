"""Database models.

SQLAlchemy only registers a table on Base.metadata once the module defining
it has been imported, and Alembic reads Base.metadata to decide what to
create. Because every model lives inside this package, importing any
submodule runs this file first, so both tables are always registered.

Re-exporting them here keeps that guarantee explicit rather than incidental,
and gives callers a single import path:

    from app.core.models import Contract

__all__ stops a linter removing imports it thinks are unused.
"""

from app.core.models.audit_event import AuditEvent
from app.core.models.base import AUTO_PK, Base
from app.core.models.contract import (
    ALL_STATUSES,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_NOT_REGISTERED,
    STATUS_REVOKED,
    Contract,
)

__all__ = [
    "AUTO_PK",
    "ALL_STATUSES",
    "AuditEvent",
    "Base",
    "Contract",
    "STATUS_ACTIVE",
    "STATUS_CANCELLED",
    "STATUS_COMPLETED",
    "STATUS_NOT_REGISTERED",
    "STATUS_REVOKED",
]
