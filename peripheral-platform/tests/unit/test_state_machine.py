from __future__ import annotations

import pytest
from peripheral_contracts import JobStatus
from peripheral_host.state_machine import (
    ALLOWED_TRANSITIONS,
    TRANSITION_EVENTS,
    InvalidStateTransition,
    can_transition,
    require_transition,
)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (source, target)
        for source, targets in ALLOWED_TRANSITIONS.items()
        for target in targets
    ],
)
def test_allowed_transition(source: JobStatus, target: JobStatus):
    assert can_transition(source, target)
    require_transition(source, target)
    assert (source, target) in TRANSITION_EVENTS


def test_succeeded_cannot_return_to_running():
    assert not can_transition(JobStatus.SUCCEEDED, JobStatus.RUNNING)

    with pytest.raises(InvalidStateTransition):
        require_transition(JobStatus.SUCCEEDED, JobStatus.RUNNING)


@pytest.mark.parametrize("terminal", [JobStatus.SUCCEEDED, JobStatus.CANCELLED])
def test_terminal_states_have_no_outgoing_transitions(terminal: JobStatus):
    assert ALLOWED_TRANSITIONS[terminal] == frozenset()
