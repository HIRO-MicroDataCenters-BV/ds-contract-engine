"""The status state machine.

Pure functions over strings — no database, no async, no HTTP. Every one of
the sixteen transitions is asserted here, which is only cheap because this
rule deliberately does not live in the repository.
"""

import pytest

from app.core.models import (
    ALL_STATUSES,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_REVOKED,
)
from app.core.status import allowed_from, can_transition

TERMINAL = (STATUS_COMPLETED, STATUS_CANCELLED, STATUS_REVOKED)


@pytest.mark.parametrize("target", TERMINAL)
def test_active_can_reach_every_terminal_state(target: str) -> None:
    assert can_transition(STATUS_ACTIVE, target)


@pytest.mark.parametrize("current", TERMINAL)
@pytest.mark.parametrize("target", ALL_STATUSES)
def test_terminal_states_go_nowhere(current: str, target: str) -> None:
    """Once a contract leaves `active` it is finished.

    Revocation is a safety mechanism; if it can be undone through the ordinary
    API then it is not one. A mistaken revocation is corrected by issuing a new
    contract, which leaves a trail.
    """
    assert not can_transition(current, target)


def test_active_cannot_go_to_active() -> None:
    """No-op transitions are refused rather than silently accepted, so a
    caller cannot use them to bump status_changed_at."""
    assert not can_transition(STATUS_ACTIVE, STATUS_ACTIVE)


def test_the_transition_that_matters_most() -> None:
    """Named explicitly so a failure says what broke, not just which pair."""
    assert not can_transition(STATUS_REVOKED, STATUS_ACTIVE)


@pytest.mark.parametrize("junk", ["", "ACTIVE", "Active", "unknown", "not_registered"])
def test_unrecognised_current_status_freezes_the_contract(junk: str) -> None:
    """An unknown status must freeze a contract, never open it up.

    Note ACTIVE and Active are refused: the Contract Validator compares status
    with strict equality, so casing is significant everywhere.
    """
    for target in ALL_STATUSES:
        assert not can_transition(junk, target)


def test_unrecognised_target_is_refused() -> None:
    assert not can_transition(STATUS_ACTIVE, "deleted")


def test_allowed_from_lists_exactly_the_terminal_states() -> None:
    assert allowed_from(STATUS_ACTIVE) == frozenset(TERMINAL)


@pytest.mark.parametrize("current", TERMINAL)
def test_allowed_from_is_empty_for_terminal_states(current: str) -> None:
    assert allowed_from(current) == frozenset()


def test_every_status_pair_is_covered() -> None:
    """Guard against a future status being added without a rule for it.

    If someone adds STATUS_SUSPENDED to ALL_STATUSES but not to the transition
    table, allowed_from() returns empty for it — safe, but silent. This makes
    the omission visible.
    """
    reachable = set()
    for s in ALL_STATUSES:
        reachable |= allowed_from(s)
    assert reachable == set(TERMINAL), (
        "A status is unreachable from anywhere. If you added one, decide "
        "which transitions reach it and update _ALLOWED in core/status.py."
    )
