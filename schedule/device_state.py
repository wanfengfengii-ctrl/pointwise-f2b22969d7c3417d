from dataclasses import dataclass, replace

SWITCH_SECONDS = 1
SAMPLE_SECONDS = 1
SETTLE_SECONDS = 1


@dataclass(frozen=True, slots=True)
class DeviceState:
    channel: str | None
    now: int
    stable_at: int


def nominal_switch_state(state: DeviceState, channel: str) -> DeviceState:
    completed_at = state.now + SWITCH_SECONDS
    return DeviceState(channel, completed_at, completed_at + SETTLE_SECONDS)


def nominal_sample_state(state: DeviceState, completed_at: int) -> DeviceState:
    return replace(state, now=completed_at)
