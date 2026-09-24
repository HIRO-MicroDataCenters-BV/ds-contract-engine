"""The history log: one row per thing that happened."""

from typing import Optional

from sqlalchemy import BigInteger, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models.base import AUTO_PK, Base


class AuditEvent(Base):
    """One thing that happened.

    Append-only by convention: the store only ever inserts. There is no hash
    chain and no signature here, so this records history but does not prove
    it was never edited. That is a deliberate scope decision.
    """

    __tablename__ = "audit_event"
    __table_args__ = (
        # The dashboard counts and the feed's commonest filter: one kind of
        # event within a time window.
        Index("ix_audit_event_event_type_occurred_at", "event_type", "occurred_at"),
    )

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
    # Indexed for "everything this person touched".
    consumer_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)

    # Who DID this — as opposed to consumer_id, who the contract is FOR. On a
    # revocation they are different people, and without this column a
    # revocation row read as though the consumer had revoked their own permit.
    #
    # Caller-asserted, not verified: this service has no authentication, so
    # it records a claim, and the admin backend that sends it is where trust
    # lives. Always "source:identity" — dev-allowlist:... today, dex:... once
    # real login lands — so that how an identity was established is stored
    # with it. In an append-only log, that cannot be added afterwards.
    actor: Mapped[Optional[str]] = mapped_column(String(255))

    # Why, in the actor's own words.
    reason: Mapped[Optional[str]] = mapped_column(String(500))

    from_status: Mapped[Optional[str]] = mapped_column(String(16))
    to_status: Mapped[Optional[str]] = mapped_column(String(16))

    occurred_at: Mapped[int] = mapped_column(BigInteger)

    # Short generated summary, e.g. "active -> revoked". Not machine-read.
    # Who and why live in actor and reason, not here.
    detail: Mapped[Optional[str]] = mapped_column(String(1024))

    def __repr__(self) -> str:
        return f"<AuditEvent {self.seq} {self.event_type}>"
