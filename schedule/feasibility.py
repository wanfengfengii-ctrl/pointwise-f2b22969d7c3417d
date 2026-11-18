from collections.abc import Sequence
from dataclasses import dataclass

from orders.tickets import Ticket

from .device_state import SAMPLE_SECONDS, SETTLE_SECONDS, SWITCH_SECONDS, DeviceState
from .windows import completion_in_window


@dataclass(frozen=True, slots=True)
class TicketReservation:
    ticket: Ticket
    switch_at: int | None
    started_at: int
    completed_at: int


def reserve_tickets(
    state: DeviceState, remaining: Sequence[Ticket]
) -> tuple[TicketReservation, ...] | None:
    queue = sorted(remaining, key=lambda ticket: (ticket.closes_at, ticket.ordinal))
    free_at, channel, ready_at = state.now, state.channel, state.stable_at
    reserved = []
    for ticket in queue:
        window_gate = max(free_at, ticket.opens_at - SAMPLE_SECONDS)
        switch_at = None
        if channel != ticket.channel:
            switch_at = window_gate
            ready_at = switch_at + SWITCH_SECONDS + SETTLE_SECONDS
            channel = ticket.channel
        started_at = max(window_gate, ready_at)
        completed_at = started_at + SAMPLE_SECONDS
        if not completion_in_window(ticket, completed_at):
            return None
        reserved.append(TicketReservation(ticket, switch_at, started_at, completed_at))
        free_at = completed_at
    return tuple(reserved)
