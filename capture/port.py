from typing import Protocol

from schedule.device_state import DeviceState

from .receipts import SampleReceipt, SwitchReceipt, WaitReceipt


class DeviceError(RuntimeError):
    pass


class DevicePort(Protocol):
    """Serial calls return actual receipt times on the snapshot's device clock."""

    def snapshot(self) -> DeviceState:
        ...

    def switch(self, channel: str) -> SwitchReceipt:
        ...

    def wait_until(self, second: int) -> WaitReceipt:
        ...

    def sample(self, ticket_id: str, channel: str) -> SampleReceipt:
        ...
