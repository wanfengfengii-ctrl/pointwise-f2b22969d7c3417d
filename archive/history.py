import sqlite3

from orders.profiles import build_profile
from orders.work_orders import WorkOrder, make_work_order

from .batches import ArchivedBatch, ArchivedSample, SuccessReceipt
from .schema import decode_exact_int
from .storage import ArchivePath, open_archive

MAX_SQLITE_ROWID = (1 << 63) - 1


class BatchNotFound(LookupError):
    pass


def _read_order(connection: sqlite3.Connection, batch: sqlite3.Row) -> WorkOrder:
    key = (batch['batch_id'],)
    channels = {
        row['channel']: (decode_exact_int(row['multiplier_hex']), decode_exact_int(row['offset_hex']))
        for row in connection.execute(
            'SELECT channel, multiplier_hex, offset_hex FROM batch_scales WHERE batch_id = ?', key
        )
    }
    profile = build_profile(batch['revision_id'], channels)
    fields = [
        (row['ticket_id'], row['channel'], row['opens_at'], row['closes_at'])
        for row in connection.execute(
            '''SELECT ticket_id, channel, opens_at, closes_at FROM batch_tickets
               WHERE batch_id = ? ORDER BY ordinal''', key
        )
    ]
    return make_work_order(batch['order_id'], profile, fields)


def _read_samples(connection: sqlite3.Connection, batch_id: int) -> tuple[ArchivedSample, ...]:
    rows = connection.execute(
        '''SELECT t.ticket_id, t.ordinal, t.channel, s.started_at, s.ended_at,
                  s.raw_count_hex, s.milliunits_hex
           FROM batch_tickets AS t
           JOIN samples AS s ON s.batch_id = t.batch_id AND s.ticket_id = t.ticket_id
           WHERE t.batch_id = ?
           ORDER BY t.ordinal''',
        (batch_id,),
    )
    return tuple(
        ArchivedSample(
            row['ticket_id'], row['ordinal'], row['channel'], row['started_at'], row['ended_at'],
            decode_exact_int(row['raw_count_hex']), decode_exact_int(row['milliunits_hex']),
        )
        for row in rows
    )


def read(path: ArchivePath, batch_id: int) -> ArchivedBatch:
    if type(batch_id) is not int or not 1 <= batch_id <= MAX_SQLITE_ROWID:
        raise BatchNotFound('batch ID must be a positive SQLite row ID')
    with open_archive(path) as connection, connection:
        connection.execute('BEGIN')
        batch = connection.execute(
            '''SELECT b.batch_id, b.order_id, b.revision_id, r.receipt_id
               FROM batches AS b JOIN success_receipts AS r ON r.batch_id = b.batch_id
               WHERE b.batch_id = ?''',
            (batch_id,),
        ).fetchone()
        if batch is None:
            raise BatchNotFound(f'no committed batch {batch_id}')
        order = _read_order(connection, batch)
        samples = _read_samples(connection, batch_id)
        receipt = SuccessReceipt(batch_id, batch['receipt_id'])
    return ArchivedBatch(order, samples, receipt)
