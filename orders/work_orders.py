from collections.abc import Sequence
from dataclasses import dataclass

from .profiles import ProfileRevision
from .tickets import Ticket, TicketFields, make_ticket
from .validation import (
    OrderInputError,
    require_distinct_ticket_ids,
    require_identifier,
    validate_ticket_count,
)


@dataclass(frozen=True, slots=True)
class WorkOrder:
    order_id: str
    profile: ProfileRevision
    tickets: tuple[Ticket, ...]


def make_work_order(
    order_id: str, profile: ProfileRevision, fields: Sequence[TicketFields]
) -> WorkOrder:
    order_id = require_identifier(order_id, 'work order ID')
    if not isinstance(fields, (list, tuple)):
        raise OrderInputError('tickets must be a finite ordered list or tuple')
    validate_ticket_count(len(fields))
    tickets = tuple(make_ticket(row, ordinal) for ordinal, row in enumerate(fields))
    require_distinct_ticket_ids(ticket.ticket_id for ticket in tickets)
    for ticket in tickets:
        profile.for_channel(ticket.channel)
    return WorkOrder(order_id, profile, tickets)
