from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Literal, TypeVar

from schedule.device_state import SAMPLE_SECONDS, SETTLE_SECONDS, SWITCH_SECONDS, DeviceState

from .port import DeviceError
from .receipts import SampleReceipt, SwitchReceipt, WaitReceipt

ActionKind = Literal['switch', 'wait', 'sample']
Receipt = SwitchReceipt | WaitReceipt | SampleReceipt
ReceiptType = TypeVar('ReceiptType', SwitchReceipt, WaitReceipt, SampleReceipt)


@dataclass(frozen=True, slots=True)
class RecordedAction:
    kind: ActionKind
    key: str | int
    raw_count: int | None = None
    extra_seconds: int = 0
    start_delay: int = 0
    actual_channel: str | None = None
    actual_ticket_id: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.kind == 'wait':
            if type(self.key) is not int or self.key < 0:
                raise ValueError('a recorded wait needs an integer target second')
        elif self.kind in ('switch', 'sample'):
            if not isinstance(self.key, str) or not self.key.strip():
                raise ValueError('a recorded switch or sample needs a channel or ticket ID')
        else:
            raise ValueError(f'unknown recorded action {self.kind!r}')
        for delay in (self.extra_seconds, self.start_delay):
            if type(delay) is not int or delay < 0:
                raise ValueError('recorded delays must be nonnegative integer seconds')


@dataclass(frozen=True, slots=True)
class ActionTrace:
    kind: ActionKind
    key: str | int
    requested_at: int
    requested_channel: str | None
    receipt: Receipt | None
    error: str | None


class RecordedPort:
    def __init__(self, initial: DeviceState, actions: Iterable[RecordedAction]) -> None:
        self._state = initial
        self._actions = tuple(actions)
        self._cursor = 0
        self._trace: list[ActionTrace] = []

    def snapshot(self) -> DeviceState:
        return self._state

    @property
    def trace(self) -> tuple[ActionTrace, ...]:
        return tuple(self._trace)

    @property
    def pending_actions(self) -> int:
        return len(self._actions) - self._cursor

    def _take(self, kind: ActionKind, key: str | int) -> RecordedAction:
        upcoming = self._actions[self._cursor] if self.pending_actions else None
        if kind == 'wait' and (upcoming is None or upcoming.kind != 'wait'):
            return RecordedAction('wait', key)
        if upcoming is None:
            raise DeviceError(f'recording exhausted before {kind} {key!r}')
        if (upcoming.kind, upcoming.key) != (kind, key):
            raise DeviceError(f'expected {upcoming.kind} {upcoming.key!r}, got {kind} {key!r}')
        self._cursor += 1
        if upcoming.error is not None:
            raise DeviceError(upcoming.error)
        return upcoming

    def _perform(
        self,
        kind: ActionKind,
        key: str | int,
        channel: str | None,
        record_receipt: Callable[[RecordedAction, int], ReceiptType],
    ) -> ReceiptType:
        requested_at = self._state.now
        try:
            record = self._take(kind, key)
        except DeviceError as error:
            self._trace.append(ActionTrace(kind, key, requested_at, channel, None, str(error)))
            raise
        receipt = record_receipt(record, requested_at + record.start_delay)
        if isinstance(receipt, SwitchReceipt):
            self._state = DeviceState(receipt.channel, receipt.ended_at, receipt.ended_at + SETTLE_SECONDS)
        else:
            self._state = replace(self._state, now=receipt.ended_at)
        self._trace.append(ActionTrace(kind, key, requested_at, channel, receipt, None))
        return receipt

    def switch(self, channel: str) -> SwitchReceipt:
        def make_receipt(record: RecordedAction, started_at: int) -> SwitchReceipt:
            actual_channel = channel if record.actual_channel is None else record.actual_channel
            return SwitchReceipt(actual_channel, started_at, started_at + SWITCH_SECONDS + record.extra_seconds)

        return self._perform('switch', channel, channel, make_receipt)

    def wait_until(self, second: int) -> WaitReceipt:
        def make_receipt(record: RecordedAction, started_at: int) -> WaitReceipt:
            channel = self._state.channel if record.actual_channel is None else record.actual_channel
            return WaitReceipt(channel, started_at, max(started_at, second) + record.extra_seconds)

        return self._perform('wait', second, self._state.channel, make_receipt)

    def sample(self, ticket_id: str, channel: str) -> SampleReceipt:
        def make_receipt(record: RecordedAction, started_at: int) -> SampleReceipt:
            actual_channel = self._state.channel if record.actual_channel is None else record.actual_channel
            actual_id = ticket_id if record.actual_ticket_id is None else record.actual_ticket_id
            ended_at = started_at + SAMPLE_SECONDS + record.extra_seconds
            return SampleReceipt(actual_id, actual_channel, started_at, ended_at, record.raw_count)

        return self._perform('sample', ticket_id, channel, make_receipt)
