"""Construct deliberately altered temporary legacy fixtures, then restore v9 guards.

Scientific adversarial tests must still exercise corrupted historical data even
though production writes now reject such edits. Never use outside test temp roots.
"""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import tempfile


@contextmanager
def fixture_connection(database):
    path = Path(database).resolve()
    if not path.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise ValueError("fixture mutation is restricted to temporary test databases")
    with sqlite3.connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        triggers = connection.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name LIKE 'immutable_%'").fetchall()
        for name, _ in triggers:
            connection.execute(f'DROP TRIGGER "{name}"')
        try:
            yield connection
        finally:
            for _, sql in triggers:
                connection.execute(sql)
