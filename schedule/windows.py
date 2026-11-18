from orders.tickets import Ticket

from .device_state import SAMPLE_SECONDS, DeviceState


def earliest_sample_times(state: DeviceState, ticket: Ticket) -> tuple[int, int]:
    started_at = max(state.now, state.stable_at, ticket.opens_at - SAMPLE_SECONDS)
    return started_at, started_at + SAMPLE_SECONDS


def completion_in_window(ticket: Ticket, completed_at: int) -> bool:
    return ticket.opens_at <= completed_at <= ticket.closes_at
