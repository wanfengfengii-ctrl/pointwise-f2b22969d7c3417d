from collections.abc import Iterator
from contextlib import contextmanager
from os import PathLike
import sqlite3

from .schema import SCHEMA_STATEMENTS

ArchivePath = str | PathLike[str]


@contextmanager
def open_archive(path: ArchivePath) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        yield connection
    finally:
        connection.close()


def initialize_archive(path: ArchivePath) -> None:
    with open_archive(path) as connection, connection:
        connection.execute('BEGIN')
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
