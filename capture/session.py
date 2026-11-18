from collections.abc import Callable
from dataclasses import replace

from archive.batches import BatchIntegrityError, SuccessReceipt, assemble_batch
from archive.commit import CommitFailure, commit_batch
from archive.storage import ArchivePath
from orders.catalog import Catalog, OrderNotFound
from orders.validation import OrderInputError
from schedule.device_state import SETTLE_SECONDS, SWITCH_SECONDS
from schedule.dispatch import NoFeasibleSuffix, reserve_actions

from .observations import InvalidObservation, ObservationLedger
from .port import DeviceError, DevicePort
from .receipts import (
    ReceiptError,
    apply_sample_receipt,
    apply_switch_receipt,
    apply_wait_receipt,
    validate_initial_state,
)


class CaptureFailure(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(detail)


def run(
    catalog: Catalog,
    order_id: str,
    device: DevicePort,
    path: ArchivePath,
    *,
    before_commit: Callable[[SuccessReceipt], None] | None = None,
) -> SuccessReceipt:
    try:
        order = catalog.get_order(order_id)
    except (OrderNotFound, OrderInputError) as error:
        raise CaptureFailure("unknown_order", str(error)) from error

    ledger = ObservationLedger(order)
    try:
        state = validate_initial_state(device.snapshot())
        for action in reserve_actions(state, ledger.remaining()):
            ticket = action.ticket
            if action.kind == "switch":
                actual = apply_switch_receipt(state, ticket.channel, device.switch(ticket.channel))
                state = replace(actual, stable_at=action.at + SWITCH_SECONDS + SETTLE_SECONDS)
            elif action.kind == "wait":
                target = action.at
                if state.now < target:
                    state = apply_wait_receipt(state, target, device.wait_until(target))
            else:
                receipt = device.sample(ticket.ticket_id, ticket.channel)
                try:
                    sampled_state = apply_sample_receipt(state, receipt)
                except ReceiptError as error:
                    raise InvalidObservation(str(error)) from error
                ledger.accept(ticket, state, receipt)
                state = sampled_state
        draft = assemble_batch(order, ledger.observations())
        return commit_batch(path, draft, before_commit=before_commit)
    except NoFeasibleSuffix as error:
        raise CaptureFailure("no_feasible_suffix", str(error)) from error
    except InvalidObservation as error:
        raise CaptureFailure("invalid_observation", str(error)) from error
    except ReceiptError as error:
        raise CaptureFailure("invalid_receipt", str(error)) from error
    except DeviceError as error:
        raise CaptureFailure("device_error", str(error)) from error
    except BatchIntegrityError as error:
        raise CaptureFailure("batch_integrity", str(error)) from error
    except CommitFailure as error:
        raise CaptureFailure("commit_failed", str(error)) from error
