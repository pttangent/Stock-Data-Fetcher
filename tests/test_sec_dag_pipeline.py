from __future__ import annotations

import json
from pathlib import Path
import tempfile
from zipfile import ZipFile

from equity_semantic_library.sec_pipeline.config import PipelineConfig, WorkerConfig
from equity_semantic_library.sec_pipeline.dag import DagPipeline
from equity_semantic_library.sec_pipeline.cli import validate_database


def _submission(form: str, filename: str, body: str) -> bytes:
    html = f"<html><body>{body}</body></html>"
    return f"""<SEC-DOCUMENT>fixture.txt
<SEC-HEADER>header</SEC-HEADER>
<DOCUMENT>
<TYPE>{form}
<SEQUENCE>1
<FILENAME>{filename}
<DESCRIPTION>primary
<TEXT>
<HTML>{html}</HTML>
</TEXT>
</DOCUMENT>
</SEC-DOCUMENT>""".encode()


def _archive(path: Path) -> None:
    filings = [
        ("10-K", "0000000001-25-000001", "annual.htm", "Item 1. Business\nWe rely on TSMC to manufacture our GPU chips. Blackwell and CUDA support data center AI.\nItem 1A. Risk Factors\nExport controls and supply chain disruption could harm us.\nItem 7. Management's Discussion and Analysis\nCapital expenditures increased."),
        ("8-K", "0000000001-25-000002", "event.htm", "Item 2.02 Results of Operations\nWe reported quarterly results.\nItem 5.02 Departure of Directors or Certain Officers\nOur chief financial officer resigned."),
        ("DEF 14A", "0000000001-25-000003", "proxy.htm", "Proposal 1\nElection of directors.\nExecutive Compensation\nAdvisory vote on executive compensation."),
        ("4", "0000000001-25-000004", "form4.xml", "ownership report"),
    ]
    with ZipFile(path, "w") as bundle:
        for index, (form, accession, filename, text) in enumerate(filings, 1):
            base = f"ticker=EX/cik=0000000001/accession={accession}"
            raw = _submission(form, filename, text)
            evidence = {"sha256": __import__("hashlib").sha256(raw).hexdigest()}
            metadata = {
                "accessionNumber": accession, "filingDate": f"2025-01-{index:02d}",
                "reportDate": "2024-12-31", "acceptanceDateTime": f"2025-01-{index:02d}T20:00:00Z",
                "form": form, "ticker": "EX", "cik": "0000000001", "companyName": "Example Corp",
                "primaryDocument": filename, "documents": {"complete": evidence},
            }
            bundle.writestr(base + "/complete-submission.txt", raw)
            bundle.writestr(base + "/complete-submission.txt.evidence.json", json.dumps(evidence))
            bundle.writestr(base + "/filing.json", json.dumps(metadata))


def test_archive_dag_excludes_ownership_and_keeps_pit_evidence() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        archive = root / "ticker=EX.zip"
        _archive(archive)
        config = PipelineConfig(
            db_path=root / "structured.db", data_dir=root / "data", sec_identity=None,
            workers=WorkerConfig(download=1, yahoo=0, parse_core=2, parse_event=1, parse_holdings=1,
                parse_other=1, semantic_core=2, semantic_event=1, semantic_holdings=1,
                semantic_other=1, finalize=1),
        )
        pipeline = DagPipeline(config)
        run_id = pipeline.create_archive_run([archive])
        result = pipeline.run(run_id)
        assert result["status"] == "completed"
        forms = {row["form"] for row in pipeline.store.query("SELECT form FROM filing")}
        assert forms == {"10-K", "8-K", "DEF 14A"}
        assert pipeline.store.query("SELECT COUNT(*) n FROM event_ledger")[0]["n"] >= 2
        assert pipeline.store.query("SELECT COUNT(*) n FROM semantic_assertion")[0]["n"] > 0
        assert pipeline.store.query("SELECT COUNT(*) n FROM company_relation WHERE target_ticker='TSM'")[0]["n"] >= 1
        evidence = pipeline.store.query("SELECT * FROM evidence_snippet LIMIT 1")[0]
        assert evidence["available_at"].startswith("2025-")
        assert evidence["source_sha256"]
        assert len(evidence["snippet"]) <= config.evidence_max_chars
        assert validate_database(pipeline.store)["passed"]
