from dataclasses import dataclass

from orders.tickets import Ticket
from orders.work_orders import WorkOrder
from schedule.device_state import DeviceState
from schedule.windows import completion_in_window

from .conversion import InvalidRawCount, convert_count
from .receipts import SampleReceipt


class InvalidObservation(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Observation:
    ticket_id: str
    channel: str
    started_at: int
    ended_at: int
    raw_count: int
    milliunits: int


class ObservationLedger:
    def __init__(self, order: WorkOrder) -> None:
        self._order = order
        self._tickets = {ticket.ticket_id: ticket for ticket in order.tickets}
        self._accepted: dict[str, Observation] = {}

    def remaining(self) -> tuple[Ticket, ...]:
        return tuple(ticket for ticket in self._order.tickets if ticket.ticket_id not in self._accepted)

    def observations(self) -> tuple[Observation, ...]:
        return tuple(self._accepted.values())

    def accept(self, ticket: Ticket, state: DeviceState, receipt: SampleReceipt) -> Observation:
        ticket_id = ticket.ticket_id
        if self._tickets.get(ticket_id) != ticket or ticket_id in self._accepted:
            raise InvalidObservation(f'ticket {ticket_id!r} is not awaiting a sample')
        if receipt.ticket_id != ticket_id:
            raise InvalidObservation(f'sample receipt does not belong to ticket {ticket_id!r}')
        if state.channel != ticket.channel or receipt.channel != ticket.channel:
            raise InvalidObservation(f'sample channel does not match ticket {ticket_id!r}')
        if receipt.started_at < state.stable_at:
            raise InvalidObservation(f'sample for {ticket_id!r} began before the channel settled')
        if not completion_in_window(ticket, receipt.ended_at):
            raise InvalidObservation(f'sample for {ticket_id!r} completed outside its window')

        scale = self._order.profile.for_channel(ticket.channel)
        try:
            milliunits = convert_count(receipt.raw_count, scale)
        except InvalidRawCount as error:
            raise InvalidObservation(f'invalid raw count for {ticket_id!r}') from error
        observation = Observation(
            ticket_id, ticket.channel, receipt.started_at, receipt.ended_at, receipt.raw_count, milliunits
        )
        self._accepted[ticket_id] = observation
        return observation
