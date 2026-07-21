from __future__ import annotations

import json
from pathlib import Path
import tempfile

from equity_semantic_library.sec_pipeline.semantic import (
    extract_offering_semantics,
    extract_proxy_semantics,
    extract_topics_and_concepts,
)
from equity_semantic_library.sec_pipeline.semantic_review import export_review_queue, import_review_decisions
from equity_semantic_library.sec_pipeline.store import PipelineStore


def _store(tmp: Path) -> PipelineStore:
    store = PipelineStore(tmp / "test.db")
    store.initialize()
    store.upsert_identity(symbol="AMD", cik="1", legal_name="Advanced Micro Devices, Inc.", metadata={})
    store.upsert_identity(symbol="GOOG", cik="2", legal_name="Alphabet Inc.", metadata={})
    store.upsert_identity(symbol="GOOGL", cik="2", legal_name="Alphabet Inc.", metadata={})
    store.upsert_identity(symbol="TSM", cik="3", legal_name="Taiwan Semiconductor Manufacturing Company Limited", metadata={})
    return store


def _filing(
    store: PipelineStore,
    *,
    filing_id: str,
    issuer_id: str,
    security_id: str,
    symbol: str,
    form: str,
    group: str,
    accession: str,
) -> dict:
    row = {
        "filing_id": filing_id,
        "issuer_id": issuer_id,
        "security_id": security_id,
        "symbol": symbol,
        "cik": issuer_id.split(":")[-1],
        "accession": accession,
        "form": form,
        "base_form": form,
        "form_group": group,
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
    store.insert_many("filing", [row])
    return row


def _section(
    store: PipelineStore,
    filing: dict,
    *,
    section_id: str,
    item: str | None,
    title: str,
    text: str,
) -> dict:
    document_id = "doc:" + section_id
    store.insert_many("filing_document", [{
        "document_id": document_id,
        "filing_id": filing["filing_id"],
        "sequence": "1",
        "document_type": filing["form"],
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
    row = {
        "section_id": section_id,
        "filing_id": filing["filing_id"],
        "document_id": document_id,
        "section_key": section_id,
        "part": None,
        "item": item,
        "title": title,
        "ordinal": 1,
        "char_start": 0,
        "char_end": len(text),
        "text": text,
        "content_hash": "d" * 64,
        "extractor_version": "test",
    }
    store.insert_many("filing_section", [row])
    return row


def test_strict_relations_and_form_policy() -> None:
    with tempfile.TemporaryDirectory() as directory:
        store = _store(Path(directory))
        amd = _filing(
            store,
            filing_id="f:amd",
            issuer_id="issuer:sec:0000000001",
            security_id="security:AMD",
            symbol="AMD",
            form="10-K",
            group="annual",
            accession="a1",
        )
        business = _section(
            store,
            amd,
            section_id="s:business",
            item="1",
            title="Business",
            text="We rely on TSMC to manufacture our processors. Intel provides incentives to customers and channel partners that compete with our products.",
        )
        counts = extract_topics_and_concepts(store, amd, [business], 800)
        assert counts["relations"] == 1
        assert store.query("SELECT target_ticker,relation_type FROM company_relation") == [
            {"target_ticker": "TSM", "relation_type": "supplier_or_manufacturer"}
        ]
        intel_candidates = store.query("SELECT status,subject_binding FROM semantic_candidate WHERE object_json LIKE '%Intel%'")
        assert intel_candidates
        assert all(row["status"] != "rule_accepted" for row in intel_candidates)

        offering = _filing(
            store,
            filing_id="f:off",
            issuer_id="issuer:sec:0000000001",
            security_id="security:AMD",
            symbol="AMD",
            form="424B5",
            group="offering",
            accession="a2",
        )
        offering_section = _section(
            store,
            offering,
            section_id="s:off",
            item=None,
            title="Prospectus",
            text="This is an invitation for subscription or purchase of debt securities. Use of proceeds will be general corporate purposes.",
        )
        extract_topics_and_concepts(store, offering, [offering_section], 800)
        extract_offering_semantics(store, offering, [offering_section], 800)
        assert store.query(
            "SELECT c.status FROM semantic_candidate c WHERE c.filing_id='f:off' AND c.object_json LIKE '%subscription_services%'"
        ) == [{"status": "review_required"}]
        assert not store.query(
            "SELECT * FROM semantic_assertion WHERE filing_id='f:off' AND object_json LIKE '%subscription_services%'"
        )
        assert store.query(
            "SELECT * FROM semantic_assertion WHERE filing_id='f:off' AND object_json LIKE '%use_of_proceeds%'"
        )

        proxy = _filing(
            store,
            filing_id="f:proxy",
            issuer_id="issuer:sec:0000000001",
            security_id="security:AMD",
            symbol="AMD",
            form="DEF 14A",
            group="proxy",
            accession="a3",
        )
        biography = _section(
            store,
            proxy,
            section_id="s:bio",
            item=None,
            title="Director Biography",
            text="Director biography and business experience: she previously served as an executive at Google Cloud. Proposal 1 is election of directors.",
        )
        extract_topics_and_concepts(store, proxy, [biography], 800)
        extract_proxy_semantics(store, proxy, [biography], 800)
        assert not store.query(
            "SELECT * FROM semantic_assertion WHERE filing_id='f:proxy' AND object_json LIKE '%Google Cloud%'"
        )
        assert store.query(
            "SELECT * FROM semantic_candidate WHERE filing_id='f:proxy' AND object_json LIKE '%Google Cloud%' AND status='review_required'"
        )


def test_issuer_security_views_and_review_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = _store(root)
        filing = _filing(
            store,
            filing_id="f:alpha",
            issuer_id="issuer:sec:0000000002",
            security_id="security:GOOGL",
            symbol="GOOGL",
            form="10-K",
            group="annual",
            accession="g1",
        )
        section = _section(
            store,
            filing,
            section_id="s:alpha",
            item="7",
            title="Management's Discussion and Analysis",
            text="Google Cloud continued to grow as customers increased use of our cloud services.",
        )
        extract_topics_and_concepts(store, filing, [section], 800)
        assert store.query(
            "SELECT DISTINCT query_symbol FROM security_semantic_assertion WHERE filing_id='f:alpha' ORDER BY query_symbol"
        ) == [{"query_symbol": "GOOG"}, {"query_symbol": "GOOGL"}]

        queue = root / "review.jsonl"
        result = export_review_queue(store, queue)
        assert result["count"] >= 1
        items = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines()]
        candidate = next(
            item
            for item in items
            if item["candidate"]["candidate_type"] == "topic"
            and item["candidate"]["object"]["topic"] == "cloud_services"
        )
        decisions = root / "decisions.jsonl"
        decisions.write_text(
            json.dumps({
                "candidate_id": candidate["candidate_id"],
                "decision": "accept",
                "rationale": "The issuer describes its own Google Cloud operating performance, so the cloud-services topic is issuer-scoped.",
            }) + "\n",
            encoding="utf-8",
        )
        imported = import_review_decisions(
            store,
            decisions,
            reviewer_type="llm",
            reviewer_id="local-model",
            reviewer_version="1",
        )
        assert imported["accepted"] == 1
        promoted = store.query(
            """SELECT a.available_at,a.subject_key,p.method
               FROM semantic_assertion a JOIN candidate_promotion p ON p.assertion_id=a.assertion_id
               WHERE p.method LIKE 'llm_review:%'"""
        )
        assert promoted
        assert promoted[0]["available_at"] == "2025-01-01T20:00:00Z"
        assert promoted[0]["subject_key"] == "issuer:sec:0000000002"
