import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from archive.history import BatchNotFound, read
from archive.storage import initialize_archive, open_archive
from capture.recording import RecordedAction, RecordedPort
from capture.session import run
from orders import Catalog
from review import InvalidThreshold, render_handoff
from review.report import report
from schedule import DeviceState


class ReviewTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / 'shift.sqlite'
        initialize_archive(self.path)
        self.catalog = Catalog()
        self.catalog.profile('R1', {'A': (2, 1), 'B': (4, -2)})

    def handoff_rows(self, result):
        return [[row.evidence.ticket_id, row.evidence.channel, row.evidence.started_at,
                 row.evidence.ended_at, row.evidence.milliunits, row.above_threshold]
                for row in result.rows]

    def test_fixed_value_and_strict_threshold(self):
        self.catalog.issue('shift', 'R1', [('T1', 'A', 0, 5), ('T2', 'A', 0, 6)])
        port = RecordedPort(DeviceState('A', 0, 0), [
            RecordedAction('sample', 'T1', raw_count=3), RecordedAction('sample', 'T2', raw_count=4),
        ])
        receipt = run(self.catalog, 'shift', port, self.path)
        self.catalog.profile('R2', {'A': (10, 0)})
        with open_archive(self.path) as connection, connection:
            connection.execute('CREATE TABLE shift_notes (note TEXT NOT NULL)')
            connection.execute('INSERT INTO shift_notes (note) VALUES (?)', ('change filter at handoff',))
        initialize_archive(self.path)
        initialize_archive(self.path)
        with open_archive(self.path) as reopened:
            self.assertEqual(reopened.execute('SELECT note FROM shift_notes').fetchone()[0], 'change filter at handoff')
        batch = read(self.path, receipt.batch_id)
        self.assertEqual(batch.receipt, receipt)
        self.assertEqual(batch.order, self.catalog.get_order('shift'))
        self.assertEqual(batch.order.profile.for_channel('B').offset, -2)
        self.assertEqual([s.raw_count for s in batch.samples], [3, 4])
        self.assertEqual([(a.key, a.receipt.ended_at) for a in port.trace], [('T1', 1), ('T2', 2)])
        result = report(self.path, receipt.batch_id, 7)
        self.assertEqual(self.handoff_rows(result), [['T1', 'A', 0, 1, 7, False], ['T2', 'A', 1, 2, 9, True]])
        self.assertEqual(render_handoff(result).splitlines(), [
            'batch_id\torder_id\trevision_id\tthreshold_milliunits',
            f'{receipt.batch_id}\tshift\tR1\t7',
            'ticket_id\tchannel\tstarted_at_s\tended_at_s\tmilliunits\tabove_threshold',
            'T1\tA\t0\t1\t7\tno', 'T2\tA\t1\t2\t9\tyes',
        ])

    def test_capture_order_differs(self):
        fields = [('T1', 'A', 3, 3), ('T2', 'A', 1, 1)]
        self.catalog.issue('reverse', 'R1', fields)
        port = RecordedPort(DeviceState('A', 0, 0), [
            RecordedAction('sample', 'T2', raw_count=4), RecordedAction('sample', 'T1', raw_count=3),
        ])
        receipt = run(self.catalog, 'reverse', port, self.path)
        self.catalog.profile('R2', {'A': (-10, 0)})
        initialize_archive(self.path)
        batch = read(self.path, receipt.batch_id)
        expected_trace = [['T2', 1], ['T1', 3]]
        actual_trace = [[entry.key, entry.receipt.ended_at] for entry in port.trace if entry.kind == 'sample']
        self.assertEqual(actual_trace, expected_trace)
        self.assertEqual([(s.ticket_id, s.ended_at, s.milliunits) for s in batch.samples], [('T1', 3, 7), ('T2', 1, 9)])
        expected_rows = [['T1', 'A', 2, 3, 7, False], ['T2', 'A', 0, 1, 9, True]]
        actual_rows = self.handoff_rows(report(self.path, receipt.batch_id, 7))
        self.assertEqual(actual_rows, expected_rows)
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'n9.capture_order_differs',
            'input': {'tickets': fields, 'scale': [2, 1], 'raw': {'T1': 3, 'T2': 4}, 'threshold': 7},
            'expected': expected_trace, 'actual': actual_trace,
            'downstream_expected': expected_rows, 'downstream_actual': actual_rows,
            'code_paths': ['capture/session.py', 'archive/history.py', 'review/report.py'],
            'oracle': 'Singleton windows force finishes 1 and 3 in reverse ticket order. Hand arithmetic gives 7 and 9 in work-order order.',
        }, sort_keys=True))

    def test_signed_exact_values(self):
        positive = 1 << 62
        self.catalog.profile('wide', {'A': (3, -1)})
        self.catalog.issue('wide', 'wide', [('plus', 'A', 1, 1), ('minus', 'A', 2, 2)])
        port = RecordedPort(DeviceState('A', 0, 0), [
            RecordedAction('sample', 'plus', raw_count=positive),
            RecordedAction('sample', 'minus', raw_count=-positive),
        ])
        receipt = run(self.catalog, 'wide', port, self.path)
        initialize_archive(self.path)
        batch = read(self.path, receipt.batch_id)
        expected = [13835058055282163711, -13835058055282163713]
        self.assertEqual([s.raw_count for s in batch.samples], [positive, -positive])
        self.assertEqual([s.milliunits for s in batch.samples], expected)
        self.assertTrue(all(type(s.milliunits) is int for s in batch.samples))
        at_plus = report(self.path, receipt.batch_id, expected[0])
        at_minus = report(self.path, receipt.batch_id, expected[1])
        self.assertEqual([row.above_threshold for row in at_plus.rows], [False, False])
        self.assertEqual([row.above_threshold for row in at_minus.rows], [True, False])

    def test_large_scale_snapshot_zero_and_negative_raw(self):
        magnitude = 1 << 67
        self.catalog.profile('exact', {'A': (magnitude, -magnitude)})
        self.catalog.issue('exact', 'exact', [('zero', 'A', 1, 1), ('negative', 'A', 2, 2)])
        port = RecordedPort(DeviceState('A', 0, 0), [
            RecordedAction('sample', 'zero', raw_count=0), RecordedAction('sample', 'negative', raw_count=-2),
        ])
        receipt = run(self.catalog, 'exact', port, self.path)
        initialize_archive(self.path)
        batch = read(self.path, receipt.batch_id)
        scale = batch.order.profile.for_channel('A')
        self.assertEqual((scale.multiplier, scale.offset), (magnitude, -magnitude))
        self.assertEqual([s.milliunits for s in batch.samples], [-magnitude, -3 * magnitude])

    def test_report_errors(self):
        self.catalog.issue('single', 'R1', [('T1', 'A', 1, 1)])
        port = RecordedPort(DeviceState('A', 0, 0), [RecordedAction('sample', 'T1', raw_count=0)])
        receipt = run(self.catalog, 'single', port, self.path)
        for missing in (receipt.batch_id + 1, 1 << 80, True):
            with self.subTest(batch_id=missing):
                with self.assertRaises(BatchNotFound):
                    report(self.path, missing, 0)
        for invalid in (None, False, 7.0, '7'):
            with self.subTest(threshold=invalid):
                with self.assertRaises(InvalidThreshold):
                    report(self.path, receipt.batch_id, invalid)
        self.assertEqual(self.handoff_rows(report(self.path, receipt.batch_id, 0)), [['T1', 'A', 0, 1, 1, True]])
