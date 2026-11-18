import json
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.history import read
from archive.storage import initialize_archive
from capture.recording import RecordedAction, RecordedPort
from capture.session import run
from orders import Catalog
from review import render_handoff
from review.report import report
from schedule import DeviceState


def main() -> None:
    catalog = Catalog()
    scales = {'A': (2, 1), 'B': (2, 1)}
    tickets = [('A1', 'A', 0, 5), ('B1', 'B', 0, 4)]
    catalog.profile('morning-r1', scales)
    order_id = catalog.issue('morning-recheck', 'morning-r1', tickets)
    device = RecordedPort(DeviceState('A', 0, 0), (
        RecordedAction('sample', 'A1', raw_count=3),
        RecordedAction('switch', 'B'),
        RecordedAction('sample', 'B1', raw_count=4),
    ))
    with TemporaryDirectory() as directory:
        path = Path(directory) / 'shift.sqlite'
        initialize_archive(path)
        receipt = run(catalog, order_id, device, path)
        catalog.profile('next-shift', {'A': (5, 0), 'B': (5, 0)})
        initialize_archive(path)
        batch = read(path, receipt.batch_id)
        handoff = report(path, receipt.batch_id, 7)

        expected = {
            'trace': [['sample', 'A1', 0, 1], ['switch', 'B', 1, 2], ['wait', 3, 2, 3], ['sample', 'B1', 3, 4]],
            'samples': [['A1', 'A', 0, 1, 3, 7], ['B1', 'B', 3, 4, 4, 9]],
            'revision': 'morning-r1',
            'receipt_round_trip': True,
        }
        actual = {
            'trace': [[call.kind, call.key, call.receipt.started_at, call.receipt.ended_at] for call in device.trace],
            'samples': [[sample.ticket_id, sample.channel, sample.started_at, sample.ended_at,
                         sample.raw_count, sample.milliunits] for sample in batch.samples],
            'revision': batch.order.profile.revision_id,
            'receipt_round_trip': batch.receipt == receipt,
        }
        downstream_expected = [['A1', 7, False], ['B1', 9, True]]
        downstream_actual = [[row.evidence.ticket_id, row.evidence.milliunits, row.above_threshold]
                             for row in handoff.rows]
        if actual != expected or downstream_actual != downstream_expected:
            raise AssertionError(f'sample demonstration disagreed with hand calculation: {actual!r}, {downstream_actual!r}')
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'n3',
            'input': {'initial': ['A', 0, 0], 'tickets': tickets, 'counts': [3, 4],
                      'profile': scales, 'threshold': 7},
            'expected': expected, 'actual': actual, 'downstream_expected': downstream_expected,
            'downstream_actual': downstream_actual,
            'code_paths': ['orders/catalog.py', 'schedule/feasibility.py', 'capture/session.py',
                           'archive/history.py', 'review/report.py'],
            'oracle': 'A finishes at 1, B switches at 1–2, settles at 3 and finishes at 4. Multiply by 2 and add 1, then compare strictly with 7.',
        }, sort_keys=True))
        print(f'Committed receipt {receipt.receipt_id}')
        print(render_handoff(handoff), end='')


if __name__ == '__main__':
    main()
