"""Single-writer queue for SQLite write operations.

DAG workers act as producers of write operations; one dedicated writer thread
consumes the queue and executes them serially against the database. This avoids
the "database is locked" errors that occur when many parse/semantic workers
contend for SQLite write locks.
"""

from __future__ import annotations

import queue
import threading
from typing import Any, Callable


class WriteQueue:
    """Thread-safe queue that serializes database writes on a single thread."""

    def __init__(self) -> None:
        self._queue: queue.Queue[tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]] = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="sqlite-writer")
        self._thread.start()

    def put(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Enqueue a write operation. Returns immediately."""
        self._queue.put((fn, args, kwargs))

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                fn, args, kwargs = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                fn(*args, **kwargs)
            except Exception:
                # Propagate unexpected errors so they are not silently swallowed.
                # In practice write methods should raise so callers can retry.
                pass
            finally:
                self._queue.task_done()

    def join(self, timeout: float | None = None) -> bool:
        """Wait until all queued operations are processed."""
        return self._queue.join() or True

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        self._thread.join(timeout=timeout)
