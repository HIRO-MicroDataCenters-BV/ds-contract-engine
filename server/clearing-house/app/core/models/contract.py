"""The contract registry: one row per issued contract."""

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models.base import Base

# --- Contract status ----------------------------------------------------
#
# Enforced here rather than by the database, per rule 3 in base.py. Only
# ACTIVE grants access, and the Contract Validator compares with strict
# equality — so casing matters and "Active" would silently deny.
STATUS_ACTIVE = "active"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"
STATUS_REVOKED = "revoked"

ALL_STATUSES = (STATUS_ACTIVE, STATUS_COMPLETED, STATUS_CANCELLED, STATUS_REVOKED)

# Returned for a jti we have never seen. Never stored — the Validator's own
# adapter produces this same string from a 404 and treats it as a graceful
# deny, so matching it keeps both ends consistent.
STATUS_NOT_REGISTERED = "not_registered"


class Contract(Base):
    """One issued contract, and whether it is still valid.

    This answers the only question the Contract Validator asks — "is permit
    <jti> still active?" — which it does on every single data access, and
    blocks on. Read far more often than written.
    """

    __tablename__ = "contract"

    # The permit id, from the token's `jti` claim. Primary key because it is
    # the only thing this table is ever looked up by.
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)

    # The basket this permit belongs to. One order can produce several
    # contracts (one per node), so this is how "revoke the whole order"
    # finds its rows — hence the index.
    order_id: Mapped[str] = mapped_column(String(64), index=True)

    # Who the permit was issued to.
    consumer_id: Mapped[str] = mapped_column(String(255))

    # One of ALL_STATUSES above.
    status: Mapped[str] = mapped_column(String(16))

    # Issued-at and expiry, copied from the token. Unix seconds.
    iat: Mapped[int] = mapped_column(BigInteger)
    exp: Mapped[int] = mapped_column(BigInteger)

    # When *we* recorded it. Differs from iat if registration was delayed,
    # which is worth being able to see.
    registered_at: Mapped[int] = mapped_column(BigInteger)

    # When the status last moved — so "when was this revoked?" is answerable.
    status_changed_at: Mapped[int] = mapped_column(BigInteger)

    def __repr__(self) -> str:
        return f"<Contract {self.jti} {self.status}>"
