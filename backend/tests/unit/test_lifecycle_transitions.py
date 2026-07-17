"""Restaurant lifecycle transition table (M2B): pure state-machine rules."""

import pytest

from app.domains.tenants.lifecycle import RestaurantStatus, can_transition

_S = RestaurantStatus

# Exactly the legal transitions (approved ruling 1: closure only via
# suspended → closed; closed terminal).
_LEGAL = {
    (_S.PROVISIONING, _S.ACTIVE),
    (_S.ACTIVE, _S.SUSPENDED),
    (_S.SUSPENDED, _S.ACTIVE),
    (_S.SUSPENDED, _S.CLOSED),
}


@pytest.mark.parametrize("current", list(_S))
@pytest.mark.parametrize("target", list(_S))
def test_transition_table_matches_the_approved_machine(
    current: RestaurantStatus, target: RestaurantStatus
) -> None:
    assert can_transition(current, target) is ((current, target) in _LEGAL)


def test_active_cannot_close_directly() -> None:
    assert not can_transition(_S.ACTIVE, _S.CLOSED)


def test_provisioning_cannot_close_directly() -> None:
    assert not can_transition(_S.PROVISIONING, _S.CLOSED)


def test_closed_is_terminal() -> None:
    assert all(not can_transition(_S.CLOSED, target) for target in _S)


def test_no_self_transitions() -> None:
    assert all(not can_transition(s, s) for s in _S)
