from pathlib import Path

from equity_semantic_library.config import Settings
from equity_semantic_library.providers.yahoo import YahooProvider


class FakeTicker:
    def get_info(self):
        return {
            "longName": "Berkshire Hathaway Inc.",
            "quoteType": "EQUITY",
            "exchange": "NYQ",
            "marketCap": 123,
            "bad": float("nan"),
        }


def test_yahoo_symbol_and_payload_are_normalized(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, yf_min_interval_seconds=0, yf_max_attempts=1)
    provider = YahooProvider(settings, ticker_factory=lambda symbol: FakeTicker())
    profile = provider.fetch_profile("BRK.B")
    assert profile.yahoo_symbol == "BRK-B"
    assert "bad" not in profile.payload
    assert list((tmp_path / "raw" / "yfinance" / "BRK-B").glob("*.json"))


def test_yahoo_uses_fresh_cache(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path,
        yf_min_interval_seconds=0,
        yf_max_attempts=1,
        yf_cache_ttl_hours=24,
    )
    calls = {"n": 0}

    def factory(symbol):
        calls["n"] += 1
        return FakeTicker()

    provider = YahooProvider(settings, ticker_factory=factory)
    first = provider.fetch_profile("BRK.B")
    second = provider.fetch_profile("BRK.B")
    assert first.payload == second.payload
    assert calls["n"] == 1
