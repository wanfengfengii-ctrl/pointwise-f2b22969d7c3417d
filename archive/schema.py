SCHEMA_STATEMENTS = (
    '''CREATE TABLE IF NOT EXISTS batches (
        batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT NOT NULL,
        revision_id TEXT NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS batch_scales (
        batch_id INTEGER NOT NULL REFERENCES batches(batch_id),
        channel TEXT NOT NULL,
        multiplier_hex TEXT NOT NULL,
        offset_hex TEXT NOT NULL,
        PRIMARY KEY (batch_id, channel)
    )''',
    '''CREATE TABLE IF NOT EXISTS batch_tickets (
        batch_id INTEGER NOT NULL REFERENCES batches(batch_id),
        ticket_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 0 AND 7),
        channel TEXT NOT NULL,
        opens_at INTEGER NOT NULL,
        closes_at INTEGER NOT NULL,
        CHECK (0 <= opens_at AND opens_at <= closes_at AND closes_at <= 600),
        PRIMARY KEY (batch_id, ticket_id),
        UNIQUE (batch_id, ordinal),
        FOREIGN KEY (batch_id, channel) REFERENCES batch_scales(batch_id, channel)
    )''',
    '''CREATE TABLE IF NOT EXISTS samples (
        batch_id INTEGER NOT NULL,
        ticket_id TEXT NOT NULL,
        started_at INTEGER NOT NULL CHECK (started_at >= 0),
        ended_at INTEGER NOT NULL CHECK (ended_at > started_at),
        raw_count_hex TEXT NOT NULL,
        milliunits_hex TEXT NOT NULL,
        PRIMARY KEY (batch_id, ticket_id),
        FOREIGN KEY (batch_id, ticket_id) REFERENCES batch_tickets(batch_id, ticket_id)
    )''',
    '''CREATE TABLE IF NOT EXISTS success_receipts (
        batch_id INTEGER PRIMARY KEY REFERENCES batches(batch_id),
        receipt_id TEXT NOT NULL UNIQUE
    )''',
)


def encode_exact_int(value: int) -> str:
    if type(value) is not int:
        raise TypeError('archive integer encoding requires an int')
    return format(value, 'x')


def decode_exact_int(text: str) -> int:
    return int(text, 16)
