from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Any, Callable

from .store_schema import SCHEMA_VERSION, _SCHEMA
from .store_utils import utc_now


class StoreBase:
    def __init__(self, path: str | Path, *, write_queue: Any | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.write_queue = write_queue

    def _enqueue(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Route a write operation through the single-writer queue if configured."""
        if self.write_queue is not None:
            self.write_queue.put(fn, *args, **kwargs)
        else:
            fn(*args, **kwargs)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=120000")
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO schema_migration(version,applied_at) VALUES(?,?)",
                (SCHEMA_VERSION, utc_now()),
            )
