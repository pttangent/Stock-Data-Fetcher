from __future__ import annotations

from pathlib import Path
import tempfile

from equity_semantic_library.sec_pipeline.semantic import extract_topics_and_concepts
from equity_semantic_library.sec_pipeline.store import PipelineStore


def test_avgo_passive_manufacturer_binding() -> None:
    with tempfile.TemporaryDirectory() as directory:
        store = PipelineStore(Path(directory) / "test.db")
        store.initialize()
        issuer_id, security_id = store.upsert_identity(
            symbol="AVGO", cik="4", legal_name="Broadcom Inc.", metadata={}
        )
        store.upsert_identity(
            symbol="TSM",
            cik="3",
            legal_name="Taiwan Semiconductor Manufacturing Company Limited",
            metadata={},
        )
        filing = {
            "filing_id": "f:avgo",
            "issuer_id": issuer_id,
            "security_id": security_id,
            "symbol": "AVGO",
            "cik": "0000000004",
            "accession": "avgo1",
            "form": "10-K",
            "base_form": "10-K",
            "form_group": "annual",
            "filing_date": "2025-01-01",
            "report_date": "2024-12-31",
            "accepted_at": "2025-01-01T20:00:00Z",
            "available_at": "2025-01-01T20:00:00Z",
            "available_at_precision": "datetime",
            "primary_document": "x.htm",
            "source_url": "https://sec.example/x",
            "raw_storage_uri": None,
            "raw_sha256": "a" * 64,
            "raw_bytes": 1,
            "compressed_bytes": 1,
            "retrieved_at": "2025-01-01T20:01:00Z",
            "status": "parsed",
            "metadata_json": "{}",
        }
        store.insert_many("filing", [filing])
        text = (
            "The majority of our front-end wafer manufacturing operations is outsourced "
            "to external foundries, including TSMC. TSMC, one of our CMs, manufactured "
            "approximately 95% of the wafers used in our products."
        )
        document_id = "doc:avgo"
        store.insert_many("filing_document", [{
            "document_id": document_id,
            "filing_id": filing["filing_id"],
            "sequence": "1",
            "document_type": "10-K",
            "filename": "x.htm",
            "description": "primary",
            "content_kind": "html",
            "mime_type": "text/html",
            "is_primary": 1,
            "is_attachment": 0,
            "source_start_byte": 0,
            "source_end_byte": len(text),
            "raw_sha256": "b" * 64,
            "payload_sha256": "c" * 64,
            "payload_bytes": len(text),
            "storage_uri": None,
        }])
        section = {
            "section_id": "s:avgo-business",
            "filing_id": filing["filing_id"],
            "document_id": document_id,
            "section_key": "item-1",
            "part": None,
            "item": "1",
            "title": "Business",
            "ordinal": 1,
            "char_start": 0,
            "char_end": len(text),
            "text": text,
            "content_hash": "d" * 64,
            "extractor_version": "test",
        }
        store.insert_many("filing_section", [section])

        counts = extract_topics_and_concepts(store, filing, [section], 800)

        assert counts["relations"] >= 1
        relations = store.query(
            "SELECT target_ticker,relation_type,status FROM company_relation WHERE filing_id=?",
            (filing["filing_id"],),
        )
        assert relations
        assert all(row["target_ticker"] == "TSM" for row in relations)
        assert all(row["relation_type"] == "supplier_or_manufacturer" for row in relations)
        assert not store.query(
            "SELECT * FROM semantic_candidate WHERE filing_id=? "
            "AND object_json LIKE '%TSM%' AND object_json LIKE '%customer_or_channel%'",
            (filing["filing_id"],),
        )
