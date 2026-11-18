from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from archive.history import read
from archive.storage import initialize_archive, open_archive
from capture.recording import RecordedAction, RecordedPort
from capture.session import CaptureFailure, run
from orders import Catalog
from schedule import DeviceState


MARKER = "CAPTURE_WINDOW_INCIDENT"


class CaptureIncidentTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / "shift.sqlite"
        initialize_archive(self.path)
        self.catalog = Catalog()
        self.catalog.profile("morning", {"A": (2, 1), "B": (2, 1)})

    def port(self, windows, actions):
        a_window, b_window = windows
        self.catalog.issue("recheck", "morning", [
            ("A1", "A", *a_window), ("B1", "B", *b_window),
        ])
        return RecordedPort(DeviceState("A", 0, 0), actions)

    def physical_actions(self, port):
        return [(entry.kind, entry.key, entry.receipt.started_at, entry.receipt.ended_at)
                for entry in port.trace if entry.kind != "wait"]

    def check_success(self, port, expected_actions, expected_samples):
        try:
            receipt = run(self.catalog, "recheck", port, self.path)
        except CaptureFailure as error:
            if error.code != "no_feasible_suffix":
                raise
            self.fail(f"{MARKER} feasible recording was refused: {error}")
        batch = read(self.path, receipt.batch_id)
        self.assertEqual(batch.receipt, receipt)
        self.assertEqual(self.physical_actions(port), expected_actions, MARKER)
        self.assertEqual([(row.ticket_id, row.channel, row.started_at, row.ended_at, row.milliunits)
                          for row in batch.samples], expected_samples, MARKER)

    def test_complete_nominal_order(self):
        port = self.port(((0, 5), (0, 4)), [
            RecordedAction("sample", "A1", raw_count=3),
            RecordedAction("switch", "B"),
            RecordedAction("sample", "B1", raw_count=4),
        ])
        self.check_success(port, [
            ("sample", "A1", 0, 1), ("switch", "B", 1, 2), ("sample", "B1", 3, 4),
        ], [("A1", "A", 0, 1, 7), ("B1", "B", 3, 4, 9)])

    def test_switch_can_start_before_completion_window(self):
        port = self.port(((0, 6), (3, 3)), [
            RecordedAction("switch", "B"),
            RecordedAction("sample", "B1", raw_count=4),
            RecordedAction("switch", "A"),
            RecordedAction("sample", "A1", raw_count=3),
        ])
        self.check_success(port, [
            ("switch", "B", 0, 1), ("sample", "B1", 2, 3),
            ("switch", "A", 3, 4), ("sample", "A1", 5, 6),
        ], [("A1", "A", 5, 6, 7), ("B1", "B", 2, 3, 9)])

    def test_late_switch_blocks_unsettled_sample(self):
        port = self.port(((0, 4), (0, 4)), [
            RecordedAction("sample", "A1", raw_count=3),
            RecordedAction("switch", "B", extra_seconds=1),
            RecordedAction("sample", "B1", raw_count=4),
        ])
        try:
            receipt = run(self.catalog, "recheck", port, self.path)
        except CaptureFailure as error:
            if error.code not in ("no_feasible_suffix", "invalid_observation"):
                raise
            self.assertEqual(error.code, "no_feasible_suffix", MARKER)
        else:
            batch = read(self.path, receipt.batch_id)
            samples = [(row.ticket_id, row.started_at, row.ended_at) for row in batch.samples]
            self.fail(f"{MARKER} unexpected successful receipt {receipt.receipt_id}: {samples!r}")
        self.assertEqual(self.physical_actions(port), [
            ("sample", "A1", 0, 1), ("switch", "B", 1, 3),
        ], MARKER)
        with open_archive(self.path) as connection:
            for table in ("batches", "batch_scales", "batch_tickets", "samples", "success_receipts"):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                                 0, f"{MARKER} partial archive in {table}")
