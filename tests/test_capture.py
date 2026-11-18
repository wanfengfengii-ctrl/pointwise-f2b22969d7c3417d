from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from archive.history import read
from archive.storage import initialize_archive, open_archive
from capture.recording import RecordedAction, RecordedPort
from capture.session import CaptureFailure, run
from orders import Catalog
from schedule import DeviceState


class CaptureTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / 'shift.sqlite'
        initialize_archive(self.path)
        self.catalog = Catalog()
        self.catalog.profile('R1', {'A': (2, 1), 'B': (2, 1), 'C': (1, 0)})

    def two_channels(self, a_window=(0, 5), b_window=(0, 4), **recording_options):
        self.catalog.issue('morning', 'R1', [('A1', 'A', *a_window), ('B1', 'B', *b_window)])
        return RecordedPort(DeviceState('A', 0, 0), [
            RecordedAction('sample', 'A1', raw_count=3),
            RecordedAction('switch', 'B', extra_seconds=recording_options.get('switch_delay', 0)),
            RecordedAction('sample', 'B1', raw_count=4,
                           extra_seconds=recording_options.get('sample_delay', 0),
                           actual_channel=recording_options.get('actual_channel')),
        ])

    def action_times(self, port):
        return [(action.kind, action.key, action.receipt.started_at, action.receipt.ended_at)
                for action in port.trace]

    def assert_empty_archive(self):
        with open_archive(self.path) as connection:
            for table in ('batches', 'batch_scales', 'batch_tickets', 'samples', 'success_receipts'):
                self.assertEqual(connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0, table)

    def test_feasible_order(self):
        port = self.two_channels()
        receipt = run(self.catalog, 'morning', port, self.path)
        batch = read(self.path, receipt.batch_id)
        self.assertEqual(batch.receipt, receipt)
        self.assertEqual(self.action_times(port), [
            ('sample', 'A1', 0, 1), ('switch', 'B', 1, 2), ('wait', 3, 2, 3), ('sample', 'B1', 3, 4),
        ])
        self.assertEqual([(s.ticket_id, s.channel, s.started_at, s.ended_at, s.raw_count, s.milliunits)
                          for s in batch.samples], [('A1', 'A', 0, 1, 3, 7), ('B1', 'B', 3, 4, 4, 9)])
        self.assertEqual(port.pending_actions, 0)

    def test_wait_for_window(self):
        port = self.two_channels(a_window=(3, 5), b_window=(0, 6))
        receipt = run(self.catalog, 'morning', port, self.path)
        self.assertEqual(self.action_times(port), [
            ('wait', 2, 0, 2), ('sample', 'A1', 2, 3), ('switch', 'B', 3, 4),
            ('wait', 5, 4, 5), ('sample', 'B1', 5, 6),
        ])
        self.assertEqual([s.ended_at for s in read(self.path, receipt.batch_id).samples], [3, 6])

    def test_distinct_same_channel(self):
        self.catalog.issue('same', 'R1', [('T1', 'A', 3, 3), ('T2', 'A', 1, 1)])
        port = RecordedPort(DeviceState('A', 0, 0), [
            RecordedAction('sample', 'T2', raw_count=4), RecordedAction('sample', 'T1', raw_count=3),
        ])
        receipt = run(self.catalog, 'same', port, self.path)
        self.assertEqual(self.action_times(port), [
            ('sample', 'T2', 0, 1), ('wait', 2, 1, 2), ('sample', 'T1', 2, 3),
        ])
        self.assertEqual([(s.ticket_id, s.raw_count, s.ended_at) for s in read(self.path, receipt.batch_id).samples],
                         [('T1', 3, 3), ('T2', 4, 1)])

    def test_late_switch_rejects_suffix(self):
        port = self.two_channels(switch_delay=1)
        with self.assertRaises(CaptureFailure) as raised:
            run(self.catalog, 'morning', port, self.path)
        self.assertEqual(raised.exception.code, 'no_feasible_suffix')
        self.assertEqual(self.action_times(port), [('sample', 'A1', 0, 1), ('switch', 'B', 1, 3)])
        self.assertEqual(port.pending_actions, 1)
        self.assert_empty_archive()

    def test_late_switch_still_feasible(self):
        port = self.two_channels(b_window=(0, 5), switch_delay=1)
        receipt = run(self.catalog, 'morning', port, self.path)
        self.assertEqual(self.action_times(port), [
            ('sample', 'A1', 0, 1), ('switch', 'B', 1, 3), ('wait', 4, 3, 4), ('sample', 'B1', 4, 5),
        ])
        self.assertEqual([(s.ticket_id, s.started_at, s.ended_at) for s in read(self.path, receipt.batch_id).samples],
                         [('A1', 0, 1), ('B1', 4, 5)])

    def test_late_sample_rejected(self):
        port = self.two_channels(sample_delay=1)
        with self.assertRaises(CaptureFailure) as raised:
            run(self.catalog, 'morning', port, self.path)
        self.assertEqual(raised.exception.code, 'invalid_observation')
        self.assertIn('outside its window', str(raised.exception))
        self.assertEqual(self.action_times(port)[-1], ('sample', 'B1', 3, 5))
        self.assert_empty_archive()

    def test_channel_mismatch(self):
        port = self.two_channels(actual_channel='A')
        with self.assertRaises(CaptureFailure) as raised:
            run(self.catalog, 'morning', port, self.path)
        self.assertEqual(raised.exception.code, 'invalid_observation')
        self.assertIn('channel', str(raised.exception))
        self.assertEqual(self.action_times(port)[-1], ('sample', 'B1', 3, 4))
        self.assertEqual(port.trace[-1].receipt.channel, 'A')
        self.assert_empty_archive()

    def test_replans_after_delayed_sample(self):
        self.catalog.issue('three', 'R1', [('A1', 'A', 0, 4), ('B1', 'B', 0, 8), ('C1', 'C', 0, 7)])
        port = RecordedPort(DeviceState('A', 0, 0), [
            RecordedAction('sample', 'A1', raw_count=3, extra_seconds=1),
            RecordedAction('switch', 'C'), RecordedAction('sample', 'C1', raw_count=5),
            RecordedAction('switch', 'B'), RecordedAction('sample', 'B1', raw_count=4),
        ])
        receipt = run(self.catalog, 'three', port, self.path)
        self.assertEqual([row for row in self.action_times(port) if row[0] == 'sample'], [
            ('sample', 'A1', 0, 2), ('sample', 'C1', 4, 5), ('sample', 'B1', 7, 8),
        ])
        self.assertEqual([(s.ticket_id, s.ended_at) for s in read(self.path, receipt.batch_id).samples],
                         [('A1', 2), ('B1', 8), ('C1', 5)])

    def test_delayed_wait_uses_actual_second(self):
        self.catalog.issue('wait', 'R1', [('T1', 'A', 3, 4)])
        port = RecordedPort(DeviceState('A', 0, 0), [
            RecordedAction('wait', 2, extra_seconds=1), RecordedAction('sample', 'T1', raw_count=3),
        ])
        receipt = run(self.catalog, 'wait', port, self.path)
        self.assertEqual(self.action_times(port), [('wait', 2, 0, 3), ('sample', 'T1', 3, 4)])
        self.assertEqual(read(self.path, receipt.batch_id).samples[0].ended_at, 4)

    def test_unmatched_ticket_and_invalid_raw_counts(self):
        self.catalog.issue('single', 'R1', [('T1', 'A', 0, 2)])
        recordings = [RecordedAction('sample', 'T1', raw_count=3, actual_ticket_id='other')]
        recordings.extend(RecordedAction('sample', 'T1', raw_count=value) for value in (None, False, 1.0))
        for recording in recordings:
            with self.subTest(recording=recording):
                port = RecordedPort(DeviceState('A', 0, 0), [recording])
                with self.assertRaises(CaptureFailure) as raised:
                    run(self.catalog, 'single', port, self.path)
                self.assertEqual(raised.exception.code, 'invalid_observation')
                self.assertEqual(len(port.trace), 1)
                self.assert_empty_archive()

    def test_infeasible_initial_state_and_unmatched_switch(self):
        self.catalog.issue('single', 'R1', [('B1', 'B', 0, 4)])
        port = RecordedPort(DeviceState('A', 2, 2), [])
        with self.assertRaises(CaptureFailure) as raised:
            run(self.catalog, 'single', port, self.path)
        self.assertEqual(raised.exception.code, 'no_feasible_suffix')
        self.assertEqual(port.trace, ())
        port = RecordedPort(DeviceState('A', 0, 0), [RecordedAction('switch', 'B', actual_channel='C')])
        with self.assertRaises(CaptureFailure) as raised:
            run(self.catalog, 'single', port, self.path)
        self.assertEqual(raised.exception.code, 'invalid_receipt')
        self.assertEqual(self.action_times(port), [('switch', 'B', 0, 1)])
        self.assert_empty_archive()
