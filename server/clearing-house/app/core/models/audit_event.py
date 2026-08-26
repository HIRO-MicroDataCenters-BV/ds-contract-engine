"""The history log: one row per thing that happened."""

from typing import Optional

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models.base import AUTO_PK, Base


class AuditEvent(Base):
    """One thing that happened.

    Append-only by convention: the store only ever inserts. There is no hash
    chain and no signature here, so this records history but does not prove
    it was never edited. That is a deliberate scope decision.
    """

    __tablename__ = "audit_event"

    # Position in the log, assigned by the database. Two events can share a
    # timestamp, so this is what gives them an unambiguous order.
    seq: Mapped[int] = mapped_column(AUTO_PK, primary_key=True, autoincrement=True)

    # e.g. contract.registered, contract.revoked.
    event_type: Mapped[str] = mapped_column(String(64))

    # The next three are optional because not every event concerns a
    # contract: a future "service.started" or "peer.unreachable" has no
    # permit, no order and no person, and inventing values would be worse.
    jti: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    order_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    consumer_id: Mapped[Optional[str]] = mapped_column(String(255))

    from_status: Mapped[Optional[str]] = mapped_column(String(16))
    to_status: Mapped[Optional[str]] = mapped_column(String(16))

    occurred_at: Mapped[int] = mapped_column(BigInteger)

    # Short human-readable note, e.g. "revoked by admin". Not machine-read.
    detail: Mapped[Optional[str]] = mapped_column(String(1024))

    def __repr__(self) -> str:
        return f"<AuditEvent {self.seq} {self.event_type}>"
