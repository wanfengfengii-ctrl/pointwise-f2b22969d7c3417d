from collections.abc import Mapping, Sequence
from threading import Lock

from .profiles import ProfileRevision, build_profile
from .tickets import TicketFields
from .validation import OrderInputError, require_identifier
from .work_orders import WorkOrder, make_work_order


class OrderNotFound(LookupError):
    pass


class Catalog:
    def __init__(self) -> None:
        self._profiles: dict[str, ProfileRevision] = {}
        self._orders: dict[str, WorkOrder] = {}
        self._lock = Lock()

    def profile(self, revision_id: str, channels: Mapping[str, tuple[int, int]]) -> str:
        candidate = build_profile(revision_id, channels)
        with self._lock:
            existing = self._profiles.get(candidate.revision_id)
            if existing is None:
                self._profiles[candidate.revision_id] = candidate
            elif existing != candidate:
                raise OrderInputError(f'revision {revision_id!r} already has different content')
        return candidate.revision_id

    def issue(self, order_id: str, revision_id: str, fields: Sequence[TicketFields]) -> str:
        revision_id = require_identifier(revision_id, 'revision ID')
        with self._lock:
            profile = self._profiles.get(revision_id)
            if profile is None:
                raise OrderInputError(f'unknown revision {revision_id!r}')
            candidate = make_work_order(order_id, profile, fields)
            existing = self._orders.get(candidate.order_id)
            if existing is None:
                self._orders[candidate.order_id] = candidate
            elif existing != candidate:
                raise OrderInputError(f'order {order_id!r} already has different content')
        return candidate.order_id

    def get_order(self, order_id: str) -> WorkOrder:
        order_id = require_identifier(order_id, 'work order ID')
        with self._lock:
            try:
                return self._orders[order_id]
            except KeyError as error:
                raise OrderNotFound(f'unknown work order {order_id!r}') from error
