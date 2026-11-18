from collections.abc import Callable
import sqlite3

from .batches import BatchDraft, SuccessReceipt
from .schema import encode_exact_int
from .storage import ArchivePath, open_archive


class CommitFailure(RuntimeError):
    pass


def _write_batch(connection: sqlite3.Connection, draft: BatchDraft) -> SuccessReceipt:
    profile = draft.order.profile
    cursor = connection.execute(
        'INSERT INTO batches (order_id, revision_id) VALUES (?, ?)',
        (draft.order.order_id, profile.revision_id),
    )
    batch_id = cursor.lastrowid
    connection.executemany(
        '''INSERT INTO batch_scales (batch_id, channel, multiplier_hex, offset_hex)
           VALUES (?, ?, ?, ?)''',
        (
            (batch_id, scale.channel, encode_exact_int(scale.multiplier), encode_exact_int(scale.offset))
            for scale in profile.scales
        ),
    )
    connection.executemany(
        '''INSERT INTO batch_tickets (batch_id, ticket_id, ordinal, channel, opens_at, closes_at)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (
            (batch_id, ticket.ticket_id, ticket.ordinal, ticket.channel, ticket.opens_at, ticket.closes_at)
            for ticket in draft.order.tickets
        ),
    )
    connection.executemany(
        '''INSERT INTO samples (batch_id, ticket_id, started_at, ended_at, raw_count_hex, milliunits_hex)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (
            (batch_id, sample.ticket_id, sample.started_at, sample.ended_at,
             encode_exact_int(sample.raw_count), encode_exact_int(sample.milliunits))
            for sample in draft.samples
        ),
    )
    receipt = SuccessReceipt(batch_id, f'capture-{batch_id}')
    connection.execute(
        'INSERT INTO success_receipts (batch_id, receipt_id) VALUES (?, ?)',
        (receipt.batch_id, receipt.receipt_id),
    )
    return receipt


def commit_batch(
    path: ArchivePath,
    draft: BatchDraft,
    *,
    before_commit: Callable[[SuccessReceipt], None] | None = None,
) -> SuccessReceipt:
    try:
        with open_archive(path) as connection, connection:
            receipt = _write_batch(connection, draft)
            if before_commit is not None:
                try:
                    before_commit(receipt)
                except Exception as error:
                    raise CommitFailure('archive pre-commit check failed') from error
    except sqlite3.Error as error:
        raise CommitFailure(f'archive transaction failed: {error}') from error
    return receipt
