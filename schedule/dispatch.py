from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from orders.tickets import Ticket

from .device_state import SWITCH_SECONDS, DeviceState
from .feasibility import PlannedStep, plan_suffix


class NoFeasibleSuffix(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ReservedAction:
    kind: Literal["switch", "wait", "sample"]
    ticket: Ticket
    at: int


def _step_actions(state: DeviceState, step: PlannedStep) -> tuple[ReservedAction, ...]:
    actions: list[ReservedAction] = []
    free_at = state.now
    if step.switch_at is not None:
        if free_at < step.switch_at:
            actions.append(ReservedAction("wait", step.ticket, step.switch_at))
        actions.append(ReservedAction("switch", step.ticket, step.switch_at))
        free_at = step.switch_at + SWITCH_SECONDS
    if free_at < step.started_at:
        actions.append(ReservedAction("wait", step.ticket, step.started_at))
    actions.append(ReservedAction("sample", step.ticket, step.started_at))
    return tuple(actions)


def reserve_actions(state: DeviceState, remaining: Sequence[Ticket]) -> tuple[ReservedAction, ...]:
    plan = plan_suffix(state, remaining)
    if plan is None:
        ids = ", ".join(repr(ticket.ticket_id) for ticket in remaining)
        raise NoFeasibleSuffix(f"no complete suffix at second {state.now} for {ids}")
    return _step_actions(state, plan[0])
