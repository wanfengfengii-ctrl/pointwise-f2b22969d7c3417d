from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from orders.tickets import Ticket

from .device_state import SWITCH_SECONDS, DeviceState
from .feasibility import reserve_tickets


class NoFeasibleSuffix(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ReservedAction:
    kind: Literal["switch", "wait", "sample"]
    ticket: Ticket
    at: int


def reserve_actions(state: DeviceState, remaining: Sequence[Ticket]) -> tuple[ReservedAction, ...]:
    reservations = reserve_tickets(state, remaining)
    if reservations is None:
        ids = ", ".join(repr(ticket.ticket_id) for ticket in remaining)
        raise NoFeasibleSuffix(f"no complete suffix at second {state.now} for {ids}")
    free_at = state.now
    actions = []
    for slot in reservations:
        if slot.switch_at is not None:
            if free_at < slot.switch_at:
                actions.append(ReservedAction("wait", slot.ticket, slot.switch_at))
            actions.append(ReservedAction("switch", slot.ticket, slot.switch_at))
            free_at = slot.switch_at + SWITCH_SECONDS
        if free_at < slot.started_at:
            actions.append(ReservedAction("wait", slot.ticket, slot.started_at))
        actions.append(ReservedAction("sample", slot.ticket, slot.started_at))
        free_at = slot.completed_at
    return tuple(actions)
