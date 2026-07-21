from __future__ import annotations

import hashlib
import json
import os
import random
import re
import tempfile
import threading
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_NULL_STRINGS = {"", "<na>", "nan", "none", "null", "nat"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def normalize_missing(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.lower() in _NULL_STRINGS:
            return None
        return cleaned
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def normalize_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-^=]*", symbol):
        raise ValueError(f"Invalid symbol: {symbol!r}")
    return symbol


def yahoo_symbol(symbol: str) -> str:
    """Translate common class-share notation for Yahoo (BRK.B -> BRK-B)."""
    return normalize_symbol(symbol).replace(".", "-")


def sec_symbol_candidates(symbol: str) -> list[str]:
    symbol = normalize_symbol(symbol)
    values = [symbol, symbol.replace(".", "-"), symbol.replace("-", ".")]
    return list(dict.fromkeys(values))


def stable_id(namespace: str, *parts: Any) -> str:
    body = "\x1f".join("" if p is None else str(p).strip().lower() for p in parts)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]
    return f"{namespace}:{digest}"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_text(content: str) -> str:
    return sha256_bytes(content.encode("utf-8"))


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def file_is_fresh(path: Path, ttl_hours: float) -> bool:
    if not path.exists() or ttl_hours <= 0:
        return False
    modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    return datetime.now(UTC) - modified <= timedelta(hours=ttl_hours)


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class RateLimiter:
    """Thread-safe minimum-interval limiter."""

    def __init__(self, requests_per_second: float | None = None, min_interval: float | None = None):
        if min_interval is None:
            if not requests_per_second or requests_per_second <= 0:
                raise ValueError("requests_per_second must be positive")
            min_interval = 1.0 / requests_per_second
        self.min_interval = max(0.0, float(min_interval))
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self.min_interval - (now - self._last)
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


def retry_delays(attempts: int, base: float = 1.0, maximum: float = 30.0) -> list[float]:
    delays: list[float] = []
    for index in range(max(0, attempts - 1)):
        raw = min(maximum, base * (2**index))
        delays.append(raw * random.uniform(0.8, 1.2))
    return delays
