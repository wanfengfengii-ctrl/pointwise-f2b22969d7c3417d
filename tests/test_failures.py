from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from archive.history import BatchNotFound, read
from archive.storage import initialize_archive, open_archive
from capture.recording import RecordedAction, RecordedPort
from capture.session import CaptureFailure, run
from orders import Catalog
from schedule import DeviceState


class FailureTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / 'shift.sqlite'
        initialize_archive(self.path)
        self.catalog = Catalog()
        self.catalog.profile('R1', {'A': (2, 1), 'B': (2, 1)})
        self.catalog.issue('first', 'R1', [('A1', 'A', 0, 5), ('B1', 'B', 0, 4)])
        self.catalog.issue('second', 'R1', [('A1', 'A', 0, 5), ('B1', 'B', 0, 4)])

    def device(self, actions=None):
        if actions is None:
            actions = [RecordedAction('sample', 'A1', raw_count=3), RecordedAction('switch', 'B'),
                       RecordedAction('sample', 'B1', raw_count=4)]
        return RecordedPort(DeviceState('A', 0, 0), actions)

    def stored_receipts(self):
        with open_archive(self.path) as connection:
            return [tuple(row) for row in connection.execute(
                'SELECT batch_id, receipt_id FROM success_receipts ORDER BY batch_id'
            )]

    def test_device_error_after_first_sample(self):
        preexisting = run(self.catalog, 'first', self.device(), self.path)
        port = self.device([RecordedAction('sample', 'A1', raw_count=3),
                            RecordedAction('switch', 'B', error='relay jammed')])
        with self.assertRaisesRegex(CaptureFailure, 'relay jammed') as raised:
            run(self.catalog, 'second', port, self.path)
        self.assertEqual(raised.exception.code, 'device_error')
        self.assertEqual(port.trace[0].receipt.ended_at, 1)
        self.assertEqual(port.trace[1].error, 'relay jammed')
        self.assertEqual(len(port.trace), 2)
        self.assertEqual(self.stored_receipts(), [(preexisting.batch_id, preexisting.receipt_id)])
        with open_archive(self.path) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM batches').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM samples').fetchone()[0], 2)
        self.assertEqual([s.milliunits for s in read(self.path, preexisting.batch_id).samples], [7, 9])

    def test_terminal_error(self):
        port = self.device([
            RecordedAction('sample', 'A1', raw_count=3),
            RecordedAction('switch', 'B', error='relay jammed'),
            RecordedAction('switch', 'B'), RecordedAction('sample', 'B1', raw_count=4),
        ])
        with self.assertRaises(CaptureFailure) as raised:
            run(self.catalog, 'first', port, self.path)
        self.assertEqual(raised.exception.code, 'device_error')
        self.assertEqual([(entry.kind, entry.key) for entry in port.trace], [('sample', 'A1'), ('switch', 'B')])
        self.assertEqual(port.pending_actions, 2)
        self.assertEqual(self.stored_receipts(), [])
        with open_archive(self.path) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM batches').fetchone()[0], 0)

    def test_commit_preserves_history(self):
        first = run(self.catalog, 'first', self.device(), self.path)
        original = read(self.path, first.batch_id)
        seen = []
        visible_receipts = []

        def fail_before_commit(candidate):
            seen.append(candidate)
            visible_receipts.extend(self.stored_receipts())
            raise RuntimeError('write gate unavailable')

        port = self.device()
        with self.assertRaises(CaptureFailure) as raised:
            run(self.catalog, 'second', port, self.path, before_commit=fail_before_commit)
        self.assertEqual(raised.exception.code, 'commit_failed')
        self.assertEqual([(call.key, call.receipt.ended_at) for call in port.trace if call.kind == 'sample'],
                         [('A1', 1), ('B1', 4)])
        self.assertEqual(len(seen), 1)
        self.assertNotEqual(seen[0].batch_id, first.batch_id)
        expected_receipts = [(first.batch_id, first.receipt_id)]
        self.assertEqual(visible_receipts, expected_receipts)
        self.assertEqual(self.stored_receipts(), expected_receipts)
        with self.assertRaises(BatchNotFound):
            read(self.path, seen[0].batch_id)
        self.assertEqual(read(self.path, first.batch_id), original)

    def test_reopen_after_rollback(self):
        first = run(self.catalog, 'first', self.device(), self.path)
        seen = []

        def fail_before_commit(candidate):
            seen.append(candidate)
            raise RuntimeError('reject transaction')

        with self.assertRaises(CaptureFailure) as raised:
            run(self.catalog, 'second', self.device(), self.path, before_commit=fail_before_commit)
        self.assertEqual(raised.exception.code, 'commit_failed')
        self.assertEqual(len(seen), 1)
        failed = seen[0]
        initialize_archive(self.path)
        with open_archive(self.path) as reopened:
            for table in ('batches', 'batch_scales', 'batch_tickets', 'samples', 'success_receipts'):
                count = reopened.execute(f'SELECT COUNT(*) FROM {table} WHERE batch_id = ?', (failed.batch_id,))
                self.assertEqual(count.fetchone()[0], 0, table)
            self.assertEqual(reopened.execute('SELECT receipt_id FROM success_receipts').fetchone()[0], first.receipt_id)
        with self.assertRaises(BatchNotFound):
            read(self.path, failed.batch_id)
        self.assertEqual([s.milliunits for s in read(self.path, first.batch_id).samples], [7, 9])
        second = run(self.catalog, 'second', self.device(), self.path)
        self.assertNotEqual(second.batch_id, first.batch_id)
        self.assertEqual(read(self.path, second.batch_id).order.order_id, 'second')
