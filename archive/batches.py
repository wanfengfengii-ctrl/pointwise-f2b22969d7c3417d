from collections.abc import Iterable
from dataclasses import dataclass

from capture.observations import Observation
from orders.work_orders import WorkOrder


class BatchIntegrityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ArchivedSample:
    ticket_id: str
    ordinal: int
    channel: str
    started_at: int
    ended_at: int
    raw_count: int
    milliunits: int


@dataclass(frozen=True, slots=True)
class BatchDraft:
    order: WorkOrder
    samples: tuple[ArchivedSample, ...]


@dataclass(frozen=True, slots=True)
class SuccessReceipt:
    batch_id: int
    receipt_id: str


@dataclass(frozen=True, slots=True)
class ArchivedBatch:
    order: WorkOrder
    samples: tuple[ArchivedSample, ...]
    receipt: SuccessReceipt

    @property
    def batch_id(self) -> int:
        return self.receipt.batch_id


def assemble_batch(order: WorkOrder, observations: Iterable[Observation]) -> BatchDraft:
    by_ticket: dict[str, Observation] = {}
    for observation in observations:
        if observation.ticket_id in by_ticket:
            raise BatchIntegrityError(f'duplicate evidence for {observation.ticket_id!r}')
        by_ticket[observation.ticket_id] = observation
    if by_ticket.keys() != {ticket.ticket_id for ticket in order.tickets}:
        raise BatchIntegrityError('sample identities do not match the complete work order')

    samples = []
    for ticket in order.tickets:
        observation = by_ticket[ticket.ticket_id]
        if observation.channel != ticket.channel:
            raise BatchIntegrityError(f'evidence belongs to another channel for {ticket.ticket_id!r}')
        samples.append(ArchivedSample(
            observation.ticket_id,
            ticket.ordinal,
            observation.channel,
            observation.started_at,
            observation.ended_at,
            observation.raw_count,
            observation.milliunits,
        ))
    return BatchDraft(order, tuple(samples))
