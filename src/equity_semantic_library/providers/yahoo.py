from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config import Settings
from ..models import YahooProfile
from ..util import (
    RateLimiter,
    atomic_write,
    canonical_json,
    file_is_fresh,
    normalize_missing,
    retry_delays,
    utc_now,
    yahoo_symbol,
)


class YahooRequestError(RuntimeError):
    pass


class YahooProvider:
    def __init__(
        self,
        settings: Settings,
        *,
        ticker_factory: Callable[[str], Any] | None = None,
    ):
        self.settings = settings
        self.limiter = RateLimiter(min_interval=settings.yf_min_interval_seconds)
        self.ticker_factory = ticker_factory
        self.raw_dir = settings.raw_dir / "yfinance"

    def _factory(self, symbol: str) -> Any:
        if self.ticker_factory is not None:
            return self.ticker_factory(symbol)
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover - dependency path
            raise RuntimeError("yfinance is not installed") from exc
        return yf.Ticker(symbol)

    def _latest_cached(self, yf_symbol: str) -> YahooProfile | None:
        folder = self.raw_dir / yf_symbol
        files = sorted(folder.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not files or not file_is_fresh(files[0], self.settings.yf_cache_ttl_hours):
            return None
        try:
            data = json.loads(files[0].read_text(encoding="utf-8"))
            payload = data.get("payload")
            observed_at = data.get("observed_at")
            requested_symbol = data.get("requested_symbol")
            if not isinstance(payload, dict) or not observed_at or not requested_symbol:
                return None
            return YahooProfile(requested_symbol, yf_symbol, observed_at, payload)
        except (OSError, ValueError, TypeError):
            return None

    def fetch_profile(self, symbol: str, *, refresh: bool = False) -> YahooProfile:
        yf_symbol = yahoo_symbol(symbol)
        if not refresh:
            cached = self._latest_cached(yf_symbol)
            if cached is not None:
                return cached

        delays = retry_delays(self.settings.yf_max_attempts, base=2.0, maximum=60.0)
        last_error: Exception | None = None
        for attempt in range(1, self.settings.yf_max_attempts + 1):
            self.limiter.wait()
            try:
                ticker = self._factory(yf_symbol)
                info = ticker.get_info()
                if not isinstance(info, dict):
                    raise TypeError("Ticker.get_info() did not return a dict")
                payload = sanitize_payload(info)
                if not any(
                    payload.get(key) for key in ("longName", "shortName", "quoteType", "exchange")
                ):
                    raise ValueError("Yahoo returned an empty or unusable profile")
                observed_at = utc_now()
                profile = YahooProfile(symbol, yf_symbol, observed_at, payload)
                self.persist(profile)
                return profile
            except Exception as exc:
                last_error = exc
                if attempt < self.settings.yf_max_attempts:
                    time.sleep(delays[attempt - 1])
        raise YahooRequestError(
            f"yfinance failed for {symbol} after {self.settings.yf_max_attempts} attempts"
        ) from last_error

    def persist(self, profile: YahooProfile) -> Path:
        timestamp = profile.observed_at.replace(":", "").replace("+", "_")
        path = self.raw_dir / profile.yahoo_symbol / f"{timestamp}.json"
        atomic_write(
            path,
            canonical_json(
                {
                    "requested_symbol": profile.requested_symbol,
                    "yahoo_symbol": profile.yahoo_symbol,
                    "observed_at": profile.observed_at,
                    "payload": profile.payload,
                }
            ).encode("utf-8"),
        )
        return path


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            cleaned = sanitize_payload(item)
            if cleaned is not None:
                result[str(key)] = cleaned
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize_payload(item) for item in value]
    cleaned = normalize_missing(value)
    if cleaned is None or isinstance(cleaned, (str, int, float, bool)):
        return cleaned
    try:
        json.dumps(cleaned)
        return cleaned
    except TypeError:
        return str(cleaned)
