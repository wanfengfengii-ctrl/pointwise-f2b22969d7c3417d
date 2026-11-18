from dataclasses import dataclass

from .validation import OrderInputError, require_identifier, validate_window

TicketFields = tuple[str, str, int, int]


@dataclass(frozen=True, slots=True)
class Ticket:
    ticket_id: str
    channel: str
    opens_at: int
    closes_at: int
    ordinal: int


def make_ticket(fields: TicketFields, ordinal: int) -> Ticket:
    if not isinstance(fields, (tuple, list)) or len(fields) != 4:
        raise OrderInputError('a ticket needs an ID, channel, and both window bounds')
    ticket_id, channel, opens_at, closes_at = fields
    lower, upper = validate_window(opens_at, closes_at)
    return Ticket(
        require_identifier(ticket_id, 'ticket ID'),
        require_identifier(channel, 'ticket channel'),
        lower,
        upper,
        ordinal,
    )
