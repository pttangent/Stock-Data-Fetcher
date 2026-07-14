from pathlib import Path

from equity_semantic_library.config import Settings
from equity_semantic_library.db import Database
from equity_semantic_library.models import CikMatch, FilingContent, YahooProfile
from equity_semantic_library.pipeline import IngestionPipeline


class FakeSec:
    def lookup_cik(self, symbol):
        return CikMatch("0000320193", symbol, "Apple Inc.")

    def get_submissions(self, cik, refresh=False):
        return {
            "cik": "320193",
            "name": "Apple Inc.",
            "sic": "3571",
            "sicDescription": "Electronic Computers",
            "stateOfIncorporation": "CA",
            "exchanges": ["Nasdaq"],
            "filings": {
                "recent": {
                    "accessionNumber": ["0000320193-25-000079"],
                    "filingDate": ["2025-10-31"],
                    "acceptanceDateTime": ["2025-10-31T06:01:00Z"],
                    "reportDate": ["2025-09-27"],
                    "form": ["10-K"],
                    "primaryDocument": ["aapl.htm"],
                }
            },
        }

    select_latest_annual_filing = staticmethod(
        __import__(
            "equity_semantic_library.providers.sec", fromlist=["SecProvider"]
        ).SecProvider.select_latest_annual_filing
    )

    def fetch_filing_content(self, symbol, metadata):
        return FilingContent(
            metadata, "x" * 6000 + "\nITEM 1. BUSINESS\nApple sells devices.", None, "fake"
        )

    def persist_filing(self, content):
        path = Path(self.base) / "filing.txt"
        path.write_text(content.text, encoding="utf-8")
        return path, "hash", "text/plain"


class FakeYahoo:
    def fetch_profile(self, symbol, refresh=False):
        return YahooProfile(
            symbol,
            symbol,
            "2026-01-01T00:00:00+00:00",
            {"longName": "Apple Inc.", "quoteType": "EQUITY", "exchange": "NMS"},
        )


def test_pipeline_writes_structured_records(tmp_path: Path):
    settings = Settings(
        db_path=tmp_path / "db.sqlite", data_dir=tmp_path, sec_identity="Test test@example.com"
    )
    sec = FakeSec()
    sec.base = tmp_path
    db = Database(settings.db_path)
    pipeline = IngestionPipeline(
        settings, database=db, sec_provider=sec, yahoo_provider=FakeYahoo()
    )
    pipeline.initialize()
    run_id = pipeline.ingest(["AAPL"])
    assert (
        db.query("SELECT status FROM ingestion_run WHERE run_id=?", (run_id,))[0]["status"]
        == "completed"
    )
    assert db.query("SELECT cik FROM issuer")[0]["cik"] == "0000320193"
    assert db.query("SELECT COUNT(*) AS n FROM source_document")[0]["n"] == 1
    assert db.query("SELECT COUNT(*) AS n FROM filing_section")[0]["n"] >= 1
    assert db.query("SELECT COUNT(*) AS n FROM company_profile_snapshot")[0]["n"] == 1
