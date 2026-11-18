from collections.abc import Sequence
from dataclasses import dataclass

from orders.tickets import Ticket

from .device_state import SAMPLE_SECONDS, SETTLE_SECONDS, SWITCH_SECONDS, DeviceState
from .windows import completion_in_window


@dataclass(frozen=True, slots=True)
class PlannedStep:
    """One ticket in a complete, still-feasible suffix plan."""

    ticket: Ticket
    switch_at: int | None
    started_at: int
    completed_at: int


def _candidate_order(remaining: Sequence[Ticket], current_channel: str | None) -> tuple[Ticket, ...]:
    # Keeping the current channel first avoids needless switch churn; among the
    # rest, earlier completion windows are tried first (earliest-deadline first).
    return tuple(sorted(
        remaining,
        key=lambda ticket: (
            current_channel is not None and ticket.channel != current_channel,
            ticket.closes_at,
            ticket.ordinal,
        ),
    ))


def _simulate_ticket(
    state: DeviceState, ticket: Ticket
) -> tuple[PlannedStep, DeviceState] | None:
    free_at = state.now
    switch_at = None
    channel = state.channel
    ready_at = state.stable_at
    if channel != ticket.channel:
        # Switches are allowed to start before the ticket window opens.
        switch_at = free_at
        ready_at = switch_at + SWITCH_SECONDS + SETTLE_SECONDS
        channel = ticket.channel
    started_at = max(free_at, ready_at, ticket.opens_at - SAMPLE_SECONDS)
    completed_at = started_at + SAMPLE_SECONDS
    if not completion_in_window(ticket, completed_at):
        return None
    step = PlannedStep(ticket, switch_at, started_at, completed_at)
    next_state = DeviceState(channel, completed_at, ready_at)
    return step, next_state


def plan_suffix(state: DeviceState, remaining: Sequence[Ticket]) -> tuple[PlannedStep, ...] | None:
    """Return a complete feasible plan for every remaining ticket, else None.

    The serial device can serve the tickets in any order, so all orderings are
    searched. Each step is simulated on the nominal clock: a switch costs one
    nominal second and the new channel settles one second after it completes.
    """
    tickets = tuple(remaining)
    if not tickets:
        return ()

    def search(current: DeviceState, pending: tuple[Ticket, ...], steps: list[PlannedStep]):
        if not pending:
            return tuple(steps)
        for ticket in _candidate_order(pending, current.channel):
            simulated = _simulate_ticket(current, ticket)
            if simulated is None:
                continue
            step, next_state = simulated
            rest = tuple(item for item in pending if item.ticket_id != ticket.ticket_id)
            found = search(next_state, rest, [*steps, step])
            if found is not None:
                return found
        return None

    return search(state, tickets, [])
