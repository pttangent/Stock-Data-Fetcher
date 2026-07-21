from pathlib import Path

from equity_semantic_library.db import Database
from equity_semantic_library.models import FilingMetadata, FilingSection, YahooProfile


def test_database_upserts_are_idempotent(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    issuer = db.upsert_issuer(cik="320193", legal_name="Apple Inc.", identity_status="sec_resolved")
    security = db.upsert_security(issuer_id=issuer, symbol="AAPL", yahoo_symbol="AAPL")
    profile = YahooProfile("AAPL", "AAPL", "2026-01-01T00:00:00+00:00", {"longName": "Apple Inc."})
    record = db.insert_source_record(
        security_id=security,
        source="yfinance",
        source_key="AAPL",
        observed_at=profile.observed_at,
        available_at=profile.observed_at,
        payload=profile.payload,
    )
    db.insert_yahoo_profile(security, record, profile)
    db.insert_yahoo_profile(security, record, profile)
    metadata = FilingMetadata(
        cik="0000320193",
        company_name="Apple Inc.",
        form="10-K",
        filing_date="2025-10-31",
        accepted_at="2025-10-31T06:01:00Z",
        report_period="2025-09-27",
        accession_number="0000320193-25-000079",
        primary_document="aapl-20250927.htm",
        source_url="https://example.test/aapl.htm",
    )
    document = db.upsert_source_document(issuer_id=issuer, metadata=metadata)
    sections = [FilingSection("business", "Item 1", "ITEM 1 BUSINESS", 0, 15)]
    db.replace_sections(document, sections, "test-v1")
    db.replace_sections(document, sections, "test-v1")
    assert db.query("SELECT COUNT(*) AS n FROM company_profile_snapshot")[0]["n"] == 1
    assert db.query("SELECT COUNT(*) AS n FROM source_document")[0]["n"] == 1
    assert db.query("SELECT COUNT(*) AS n FROM filing_section")[0]["n"] == 1
    with db.connect() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_sec_identity_promotes_existing_provisional_security(tmp_path: Path):
    db = Database(tmp_path / "promote.db")
    db.initialize()
    provisional = db.upsert_issuer(
        cik=None,
        legal_name="Apple",
        identity_status="provisional",
        provisional_key="AAPL",
    )
    first_security = db.upsert_security(
        issuer_id=provisional, symbol="AAPL", yahoo_symbol="AAPL", status="provisional"
    )
    resolved = db.upsert_issuer(
        cik="320193", legal_name="Apple Inc.", identity_status="sec_resolved"
    )
    second_security = db.upsert_security(
        issuer_id=resolved, symbol="AAPL", yahoo_symbol="AAPL", status="active"
    )
    assert first_security == second_security
    rows = db.query(
        "SELECT s.issuer_id,i.cik,s.status FROM security s JOIN issuer i USING(issuer_id)"
    )
    assert rows == [{"issuer_id": resolved, "cik": "0000320193", "status": "active"}]
