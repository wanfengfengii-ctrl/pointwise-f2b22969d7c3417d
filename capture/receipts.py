from dataclasses import dataclass, replace

from schedule.device_state import SAMPLE_SECONDS, SETTLE_SECONDS, SWITCH_SECONDS, DeviceState


class ReceiptError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SwitchReceipt:
    channel: str
    started_at: int
    ended_at: int


@dataclass(frozen=True, slots=True)
class WaitReceipt:
    channel: str | None
    started_at: int
    ended_at: int


@dataclass(frozen=True, slots=True)
class SampleReceipt:
    ticket_id: str
    channel: str | None
    started_at: int
    ended_at: int
    raw_count: int


def validate_initial_state(state: DeviceState) -> DeviceState:
    if not isinstance(state, DeviceState):
        raise ReceiptError('device snapshot has the wrong type')
    if type(state.now) is not int or type(state.stable_at) is not int:
        raise ReceiptError('device snapshot times must be integer seconds')
    if state.now < 0 or state.stable_at < 0:
        raise ReceiptError('device snapshot times must be nonnegative')
    if state.channel is not None and (not isinstance(state.channel, str) or not state.channel.strip()):
        raise ReceiptError('invalid channel in device snapshot')
    return state


def validate_receipt_times(
    state: DeviceState, started_at: int, ended_at: int, minimum_duration: int
) -> None:
    if type(started_at) is not int or type(ended_at) is not int:
        raise ReceiptError('receipt times must be integer seconds')
    if started_at < state.now:
        raise ReceiptError('receipt started before the previous action completed')
    if ended_at < started_at + minimum_duration:
        raise ReceiptError('receipt elapsed time is shorter than the action minimum')


def apply_switch_receipt(state: DeviceState, channel: str, receipt: SwitchReceipt) -> DeviceState:
    if not isinstance(receipt, SwitchReceipt) or receipt.channel != channel:
        raise ReceiptError('switch receipt does not match the requested channel')
    validate_receipt_times(state, receipt.started_at, receipt.ended_at, SWITCH_SECONDS)
    return DeviceState(receipt.channel, receipt.ended_at, receipt.ended_at + SETTLE_SECONDS)


def apply_wait_receipt(state: DeviceState, target: int, receipt: WaitReceipt) -> DeviceState:
    if not isinstance(receipt, WaitReceipt) or receipt.channel != state.channel:
        raise ReceiptError('wait receipt changed the selected channel')
    validate_receipt_times(state, receipt.started_at, receipt.ended_at, 0)
    if receipt.ended_at < target:
        raise ReceiptError('wait receipt ended before the requested time')
    return replace(state, now=receipt.ended_at)


def apply_sample_receipt(state: DeviceState, receipt: SampleReceipt) -> DeviceState:
    if not isinstance(receipt, SampleReceipt):
        raise ReceiptError('sample receipt has the wrong type')
    validate_receipt_times(state, receipt.started_at, receipt.ended_at, SAMPLE_SECONDS)
    return replace(state, now=receipt.ended_at)
