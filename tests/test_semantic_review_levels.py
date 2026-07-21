from __future__ import annotations

import json
from pathlib import Path
import tempfile

from equity_semantic_library.sec_pipeline.semantic import (
    extract_8k_events,
    extract_topics_and_concepts,
)
from equity_semantic_library.sec_pipeline.semantic_review import (
    export_review_queue,
    import_review_decisions,
)
from equity_semantic_library.sec_pipeline.store import PipelineStore


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
    store.insert_many(
        "filing_document",
        [
            {
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
            }
        ],
    )
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


def _store(root: Path) -> tuple[PipelineStore, str, str]:
    store = PipelineStore(root / "test.db")
    store.initialize()
    issuer_id, security_id = store.upsert_identity(
        symbol="AMD",
        cik="1",
        legal_name="Advanced Micro Devices, Inc.",
        metadata={},
    )
    return store, issuer_id, security_id


def test_default_export_is_b_and_below_grouped_by_evidence() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store, issuer_id, security_id = _store(root)

        annual = _filing(
            store,
            filing_id="f:annual",
            issuer_id=issuer_id,
            security_id=security_id,
            symbol="AMD",
            form="10-K",
            group="annual",
            accession="annual1",
        )
        business = _section(
            store,
            annual,
            section_id="s:business",
            item="1",
            title="Business",
            text=(
                "We design semiconductor processors for data center systems "
                "and cloud infrastructure."
            ),
        )
        extract_topics_and_concepts(store, annual, [business], 800)

        event = _filing(
            store,
            filing_id="f:event",
            issuer_id=issuer_id,
            security_id=security_id,
            symbol="AMD",
            form="8-K",
            group="event",
            accession="event1",
        )
        event_section = _section(
            store,
            event,
            section_id="s:event",
            item="2.02",
            title="Results of Operations",
            text="The company reported quarterly results of operations.",
        )
        extract_8k_events(store, event, [event_section], 800)

        offering = _filing(
            store,
            filing_id="f:offering",
            issuer_id=issuer_id,
            security_id=security_id,
            symbol="AMD",
            form="424B5",
            group="offering",
            accession="offering1",
        )
        offering_section = _section(
            store,
            offering,
            section_id="s:offering",
            item=None,
            title="Prospectus",
            text="This invitation permits subscription or purchase of securities.",
        )
        extract_topics_and_concepts(store, offering, [offering_section], 800)

        output = root / "review.jsonl"
        report = export_review_queue(store, output)
        units = [
            json.loads(line)
            for line in output.read_text(encoding="utf-8").splitlines()
        ]
        levels = {
            candidate["promotion_level"]
            for unit in units
            for candidate in unit["candidates"]
        }

        assert "A" not in levels
        assert "B" in levels
        assert "D" in levels
        assert report["levels"] == ["B", "C", "D", "R"]
        assert report["review_units"] <= report["candidate_count"]


def test_llm_review_can_confirm_or_supersede_existing_b_outputs() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store, issuer_id, security_id = _store(root)
        annual = _filing(
            store,
            filing_id="f:annual",
            issuer_id=issuer_id,
            security_id=security_id,
            symbol="AMD",
            form="10-K",
            group="annual",
            accession="annual1",
        )
        business = _section(
            store,
            annual,
            section_id="s:business",
            item="1",
            title="Business",
            text=(
                "We design semiconductor processors for data center systems "
                "and cloud infrastructure."
            ),
        )
        extract_topics_and_concepts(store, annual, [business], 800)
        b_candidates = store.query(
            """SELECT candidate_id,object_json
               FROM semantic_candidate
               WHERE promotion_level='B'
               ORDER BY candidate_id"""
        )
        assert len(b_candidates) >= 2

        confirm_id = b_candidates[0]["candidate_id"]
        reject_id = b_candidates[1]["candidate_id"]
        assertion_count_before = store.query(
            """SELECT COUNT(*) AS n FROM candidate_promotion
               WHERE candidate_id=? AND assertion_id IS NOT NULL""",
            (confirm_id,),
        )[0]["n"]

        decisions = root / "decisions.jsonl"
        decisions.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "candidate_id": confirm_id,
                            "decision": "accept",
                            "rationale": "The issuer explicitly describes its own business.",
                        }
                    ),
                    json.dumps(
                        {
                            "candidate_id": reject_id,
                            "decision": "reject",
                            "rationale": "The evidence does not support this taxonomy label.",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        result = import_review_decisions(
            store,
            decisions,
            reviewer_type="llm",
            reviewer_id="test-model",
            reviewer_version="1",
        )

        assert result["accepted"] == 1
        assert result["confirmed_existing"] == 1
        assert result["rejected"] == 1
        assert store.query(
            "SELECT status FROM semantic_candidate WHERE candidate_id=?",
            (confirm_id,),
        ) == [{"status": "review_accepted"}]
        assert store.query(
            "SELECT status FROM semantic_candidate WHERE candidate_id=?",
            (reject_id,),
        ) == [{"status": "rejected"}]
        assert store.query(
            """SELECT DISTINCT a.status
               FROM semantic_assertion a
               JOIN candidate_promotion p ON p.assertion_id=a.assertion_id
               WHERE p.candidate_id=?""",
            (reject_id,),
        ) == [{"status": "superseded"}]

        assertion_count_after = store.query(
            """SELECT COUNT(DISTINCT assertion_id) AS n
               FROM candidate_promotion
               WHERE candidate_id=? AND assertion_id IS NOT NULL""",
            (confirm_id,),
        )[0]["n"]
        assert assertion_count_after == assertion_count_before
