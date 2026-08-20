"""The contract status state machine.

Deliberately a pure function over strings: no database, no async, no HTTP.
All sixteen transitions can be asserted in microseconds, which is the whole
reason this rule does not live in the repository.
"""

from typing import Dict, FrozenSet

from app.core.models import (
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_REVOKED,
)

# Once a contract leaves `active` it is finished.
#
# Revocation is a safety mechanism. If it can be undone through the ordinary
# API then it is not one — a mistaken revocation is corrected by issuing a new
# contract, which leaves a trail, not by quietly flipping the old one back.
_ALLOWED: Dict[str, FrozenSet[str]] = {
    STATUS_ACTIVE: frozenset({STATUS_COMPLETED, STATUS_CANCELLED, STATUS_REVOKED}),
    STATUS_COMPLETED: frozenset(),
    STATUS_CANCELLED: frozenset(),
    STATUS_REVOKED: frozenset(),
}


def can_transition(current: str, new: str) -> bool:
    """True if a contract may move from `current` to `new`.

    An unknown `current` returns False rather than raising: a status we do not
    recognise should freeze the contract, not open it up.
    """
    return new in _ALLOWED.get(current, frozenset())


def allowed_from(current: str) -> FrozenSet[str]:
    """The statuses reachable from `current`. Empty for terminal states."""
    return _ALLOWED.get(current, frozenset())
