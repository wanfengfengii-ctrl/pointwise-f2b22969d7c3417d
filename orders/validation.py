from collections.abc import Iterable

MIN_TICKETS = 1
MAX_TICKETS = 8
MAX_WINDOW_SECOND = 600


class OrderInputError(ValueError):
    pass


def require_identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OrderInputError(f'{name} must be a nonempty string')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as error:
        raise OrderInputError(f'{name} must be valid UTF-8 text') from error
    return value


def require_integer(value: object, name: str) -> int:
    if type(value) is not int:
        raise OrderInputError(f'{name} must be an integer')
    return value


def validate_window(opens_at: object, closes_at: object) -> tuple[int, int]:
    lower = require_integer(opens_at, 'window lower bound')
    upper = require_integer(closes_at, 'window upper bound')
    if not 0 <= lower <= upper <= MAX_WINDOW_SECOND:
        raise OrderInputError(f'window must lie in [0, {MAX_WINDOW_SECOND}]')
    return lower, upper


def validate_ticket_count(count: int) -> None:
    if not MIN_TICKETS <= count <= MAX_TICKETS:
        raise OrderInputError(f'an order needs {MIN_TICKETS} to {MAX_TICKETS} tickets')


def require_distinct_ticket_ids(ticket_ids: Iterable[str]) -> None:
    seen: set[str] = set()
    for ticket_id in ticket_ids:
        if ticket_id in seen:
            raise OrderInputError(f'duplicate ticket ID {ticket_id!r}')
        seen.add(ticket_id)
