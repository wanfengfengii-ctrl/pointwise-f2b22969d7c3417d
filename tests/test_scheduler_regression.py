from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from archive.history import read
from archive.storage import initialize_archive, open_archive
from capture.recording import RecordedAction, RecordedPort
from capture.session import CaptureFailure, run
from orders import Catalog
from schedule import DeviceState


class SchedulerRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / "shift.sqlite"
        initialize_archive(self.path)
        self.catalog = Catalog()
        self.catalog.profile("morning", {"A": (2, 1), "B": (2, 1), "C": (1, 0)})

    def trace(self, port):
        return [
            (entry.kind, entry.key, entry.receipt.started_at, entry.receipt.ended_at)
            for entry in port.trace
        ]

    def physical_trace(self, port):
        return [entry for entry in self.trace(port) if entry[0] != "wait"]

    def test_deadline_ordering_beats_original_ticket_order(self):
        # A1 has the earlier ordinal but the later window; only the B-first
        # ordering keeps both tickets inside their completion windows.
        self.catalog.issue("recheck", "morning", [
            ("A1", "A", 0, 6), ("B1", "B", 3, 3),
        ])
        port = RecordedPort(DeviceState("A", 0, 0), [
            RecordedAction("switch", "B"),
            RecordedAction("sample", "B1", raw_count=4),
            RecordedAction("switch", "A"),
            RecordedAction("sample", "A1", raw_count=3),
        ])
        receipt = run(self.catalog, "recheck", port, self.path)
        self.assertEqual(self.physical_trace(port), [
            ("switch", "B", 0, 1), ("sample", "B1", 2, 3),
            ("switch", "A", 3, 4), ("sample", "A1", 5, 6),
        ])
        # Archived evidence always stays in the original ticket order.
        self.assertEqual(
            [(s.ticket_id, s.ended_at, s.milliunits) for s in read(self.path, receipt.batch_id).samples],
            [("A1", 6, 7), ("B1", 3, 9)],
        )

    def test_switch_starts_before_window_opens(self):
        # The switch happens while both windows are still closed; only the
        # sample completion has to land inside the ticket's closed interval.
        self.catalog.issue("early", "morning", [("B1", "B", 3, 4)])
        port = RecordedPort(DeviceState("A", 0, 0), [
            RecordedAction("switch", "B"),
            RecordedAction("sample", "B1", raw_count=4),
        ])
        receipt = run(self.catalog, "early", port, self.path)
        self.assertEqual(self.trace(port), [
            ("switch", "B", 0, 1),
            ("wait", 2, 1, 2),
            ("sample", "B1", 2, 3),
        ])
        self.assertEqual(self.physical_trace(port), [
            ("switch", "B", 0, 1), ("sample", "B1", 2, 3),
        ])
        self.assertEqual(read(self.path, receipt.batch_id).samples[0].milliunits, 9)

    def test_late_switch_replans_without_dispatching_sample(self):
        self.catalog.issue("late", "morning", [
            ("A1", "A", 0, 4), ("B1", "B", 0, 4),
        ])
        port = RecordedPort(DeviceState("A", 0, 0), [
            RecordedAction("sample", "A1", raw_count=3),
            RecordedAction("switch", "B", extra_seconds=1),
            RecordedAction("sample", "B1", raw_count=4),
        ])
        with self.assertRaises(CaptureFailure) as raised:
            run(self.catalog, "late", port, self.path)
        self.assertEqual(raised.exception.code, "no_feasible_suffix")
        # B1's sample must never be attempted once the late receipt lands.
        self.assertEqual(self.physical_trace(port), [
            ("sample", "A1", 0, 1), ("switch", "B", 1, 3),
        ])
        self.assertEqual(port.pending_actions, 1)
        with open_archive(self.path) as connection:
            for table in ("batches", "batch_scales", "batch_tickets", "samples", "success_receipts"):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)

    def test_late_switch_with_slack_uses_actual_settle_second(self):
        self.catalog.issue("slack", "morning", [
            ("A1", "A", 0, 5), ("B1", "B", 0, 6),
        ])
        port = RecordedPort(DeviceState("A", 0, 0), [
            RecordedAction("sample", "A1", raw_count=3),
            RecordedAction("switch", "B", extra_seconds=1),
            RecordedAction("sample", "B1", raw_count=4),
        ])
        receipt = run(self.catalog, "slack", port, self.path)
        self.assertEqual(self.trace(port), [
            ("sample", "A1", 0, 1),
            ("switch", "B", 1, 3),
            ("wait", 4, 3, 4),
            ("sample", "B1", 4, 5),
        ])
        self.assertEqual(
            [(s.ticket_id, s.started_at, s.ended_at) for s in read(self.path, receipt.batch_id).samples],
            [("A1", 0, 1), ("B1", 4, 5)],
        )

    def test_same_channel_tickets_keep_independent_samples(self):
        self.catalog.issue("same", "morning", [
            ("T1", "A", 3, 3), ("T2", "A", 1, 1),
        ])
        port = RecordedPort(DeviceState("A", 0, 0), [
            RecordedAction("sample", "T2", raw_count=4),
            RecordedAction("sample", "T1", raw_count=3),
        ])
        receipt = run(self.catalog, "same", port, self.path)
        self.assertEqual(self.physical_trace(port), [
            ("sample", "T2", 0, 1), ("sample", "T1", 2, 3),
        ])
        self.assertEqual(
            [(s.ticket_id, s.started_at, s.ended_at, s.raw_count, s.milliunits)
             for s in read(self.path, receipt.batch_id).samples],
            [("T1", 2, 3, 3, 7), ("T2", 0, 1, 4, 9)],
        )

    def test_delayed_receipt_reorders_remaining_suffix(self):
        # A1 overruns its nominal second; the planner then serves C1 before B1
        # because B1's window is the wider one.
        self.catalog.issue("three", "morning", [
            ("A1", "A", 0, 4), ("B1", "B", 0, 8), ("C1", "C", 0, 7),
        ])
        port = RecordedPort(DeviceState("A", 0, 0), [
            RecordedAction("sample", "A1", raw_count=3, extra_seconds=1),
            RecordedAction("switch", "C"),
            RecordedAction("sample", "C1", raw_count=5),
            RecordedAction("switch", "B"),
            RecordedAction("sample", "B1", raw_count=4),
        ])
        receipt = run(self.catalog, "three", port, self.path)
        self.assertEqual(self.physical_trace(port), [
            ("sample", "A1", 0, 2),
            ("switch", "C", 2, 3),
            ("sample", "C1", 4, 5),
            ("switch", "B", 5, 6),
            ("sample", "B1", 7, 8),
        ])
        self.assertEqual(
            [(s.ticket_id, s.ended_at) for s in read(self.path, receipt.batch_id).samples],
            [("A1", 2), ("B1", 8), ("C1", 5)],
        )

    def test_committed_batch_survives_new_revision_and_archive_reopen(self):
        self.catalog.issue("fixed", "morning", [("A1", "A", 0, 5)])
        port = RecordedPort(DeviceState("A", 0, 0), [
            RecordedAction("sample", "A1", raw_count=3),
        ])
        receipt = run(self.catalog, "fixed", port, self.path)
        self.catalog.profile("next-revision", {"A": (99, 99), "B": (1, 0)})
        initialize_archive(self.path)
        batch = read(self.path, receipt.batch_id)
        self.assertEqual(batch.receipt, receipt)
        self.assertEqual(batch.order.profile.revision_id, "morning")
        self.assertEqual(batch.samples[0].milliunits, 7)

    def test_failed_capture_keeps_previous_batch_readable(self):
        self.catalog.issue("first", "morning", [("A1", "A", 0, 5)])
        first = run(
            self.catalog, "first",
            RecordedPort(DeviceState("A", 0, 0), [
                RecordedAction("sample", "A1", raw_count=3),
            ]),
            self.path,
        )
        self.catalog.issue("second", "morning", [
            ("A1", "A", 0, 4), ("B1", "B", 0, 4),
        ])
        port = RecordedPort(DeviceState("A", 0, 0), [
            RecordedAction("sample", "A1", raw_count=3),
            RecordedAction("switch", "B", extra_seconds=1),
            RecordedAction("sample", "B1", raw_count=4),
        ])
        with self.assertRaises(CaptureFailure) as raised:
            run(self.catalog, "second", port, self.path)
        self.assertEqual(raised.exception.code, "no_feasible_suffix")
        prior = read(self.path, first.batch_id)
        self.assertEqual(prior.receipt, first)
        self.assertEqual([s.ticket_id for s in prior.samples], ["A1"])
        with open_archive(self.path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM success_receipts").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
