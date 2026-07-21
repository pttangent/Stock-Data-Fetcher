from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .config import PipelineConfig
from .dag import DagPipeline
from .semantic_review import export_review_queue, import_review_decisions
from .store import PipelineStore


def _config(args: argparse.Namespace, *, require_sec: bool) -> PipelineConfig:
    overrides = {}
    if getattr(args, "db", None):
        overrides["db_path"] = Path(args.db)
    if getattr(args, "data_dir", None):
        overrides["data_dir"] = Path(args.data_dir)
    if getattr(args, "metadata", None):
        overrides["symbol_metadata_path"] = Path(args.metadata)
    if getattr(args, "from_date", None):
        overrides["from_date"] = args.from_date
    if getattr(args, "to_date", None):
        overrides["to_date"] = args.to_date
    config = (
        PipelineConfig.from_json(args.config, **overrides)
        if getattr(args, "config", None)
        else PipelineConfig.from_env(**overrides)
    )
    config.validate(require_sec=require_sec)
    return config


def _mode(args: argparse.Namespace) -> str:
    return getattr(args, "mode", "all")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="esl-sec",
        description="Multi-worker SEC/Yfinance DAG pipeline",
    )
    parser.add_argument("--config", help="JSON pipeline configuration")
    parser.add_argument("--db", help="Separate pipeline SQLite database path")
    parser.add_argument("--data-dir", help="Raw/cache/run data directory")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Initialize the separate pipeline database")
    run = sub.add_parser(
        "run",
        help="Read symbol metadata and run the online or local structure pipeline",
    )
    run.add_argument("--metadata", help="Read-only symbol_metadata.parquet or CSV")
    run.add_argument("--limit", type=int)
    run.add_argument("--from-date", help="Filing date lower bound YYYY-MM-DD")
    run.add_argument("--to-date", help="Filing date upper bound YYYY-MM-DD")
    run.add_argument(
        "--mode",
        choices=["all", "download", "structure"],
        default="all",
        help=(
            "all=download+parse+semantic; download=raw SEC only; "
            "structure=parse/semantic existing downloads"
        ),
    )
    run.add_argument(
        "--rebuild-semantic",
        action="store_true",
        help=(
            "In structure mode, also rebuild semantic output for filings "
            "already marked structured"
        ),
    )
    run.add_argument("--refresh", action="store_true")
    run.add_argument("--no-yahoo", action="store_true")
    archive = sub.add_parser(
        "import-archive",
        help="Run deterministic structure/semantic workers on existing ticker ZIP archives",
    )
    archive.add_argument("archives", nargs="+")
    archive.add_argument(
        "--symbol",
        help="Fallback symbol when archive metadata lacks ticker",
    )
    resume = sub.add_parser("resume", help="Resume a persistent DAG run")
    resume.add_argument("run_id")
    status = sub.add_parser("status", help="Show a run and task counts")
    status.add_argument("run_id")
    validate = sub.add_parser("validate", help="Run database governance checks")
    validate.add_argument("--output")
    inspect = sub.add_parser(
        "inspect",
        help="Inspect issuer-level output through a ticker/security view",
    )
    inspect.add_argument("symbol")
    review_export = sub.add_parser(
        "review-export",
        help=(
            "Export unreviewed semantic candidates as evidence-grouped JSONL; "
            "defaults to B/C/D/R"
        ),
    )
    review_export.add_argument("--output", required=True)
    review_export.add_argument(
        "--limit",
        type=int,
        help="Maximum evidence review units, not candidate rows",
    )
    review_export.add_argument(
        "--status",
        action="append",
        choices=[
            "pending",
            "rule_accepted",
            "review_required",
            "review_accepted",
            "rejected",
            "superseded",
        ],
        help=(
            "Candidate status to include; repeat as needed. "
            "Default: rule_accepted, review_required, rejected"
        ),
    )
    review_export.add_argument(
        "--level",
        action="append",
        choices=["A", "B", "C", "D", "R"],
        help="Promotion level to include; repeat as needed. Default: B,C,D,R",
    )
    review_export.add_argument(
        "--include-reviewed",
        action="store_true",
        help="Also export candidates that already have semantic_review rows",
    )
    review_export.add_argument(
        "--no-dedupe-evidence",
        action="store_true",
        help="Export one JSONL unit per candidate instead of grouping shared evidence",
    )
    review_import = sub.add_parser(
        "review-import",
        help="Import human/LLM candidate decisions from JSONL",
    )
    review_import.add_argument("--input", required=True)
    review_import.add_argument(
        "--reviewer-type",
        choices=["llm", "human"],
        required=True,
    )
    review_import.add_argument("--reviewer-id", required=True)
    review_import.add_argument("--reviewer-version")
    return parser


def validate_database(store: PipelineStore) -> dict:
    checks = {}
    with store.connect() as conn:
        checks["quick_check"] = conn.execute("PRAGMA quick_check").fetchone()[0]
        checks["ownership_forms"] = conn.execute(
            "SELECT COUNT(*) FROM filing WHERE base_form IN ('3','4','5','144')"
        ).fetchone()[0]
        checks["missing_available_at"] = conn.execute(
            "SELECT COUNT(*) FROM filing "
            "WHERE available_at IS NULL OR available_at=''"
        ).fetchone()[0]
        checks["missing_evidence_time"] = conn.execute(
            "SELECT COUNT(*) FROM evidence_snippet "
            "WHERE available_at IS NULL OR observed_at IS NULL"
        ).fetchone()[0]
        checks["orphan_assertions"] = conn.execute(
            "SELECT COUNT(*) FROM semantic_assertion a "
            "LEFT JOIN evidence_snippet e ON e.evidence_id=a.evidence_id "
            "WHERE e.evidence_id IS NULL"
        ).fetchone()[0]
        checks["orphan_candidates"] = conn.execute(
            "SELECT COUNT(*) FROM semantic_candidate c "
            "LEFT JOIN evidence_snippet e ON e.evidence_id=c.evidence_id "
            "WHERE e.evidence_id IS NULL"
        ).fetchone()[0]
        checks["accepted_without_promotion"] = conn.execute(
            """SELECT COUNT(*) FROM semantic_candidate c
               LEFT JOIN candidate_promotion p
                 ON p.candidate_id=c.candidate_id
               WHERE c.status IN ('rule_accepted','review_accepted')
                 AND p.candidate_id IS NULL"""
        ).fetchone()[0]
        checks["self_target_relations"] = conn.execute(
            """SELECT COUNT(*) FROM company_relation r
               JOIN security s ON s.symbol=r.target_ticker
               WHERE s.issuer_id=r.source_issuer_id
                 AND r.status='accepted'"""
        ).fetchone()[0]
        checks["sha_mismatch_issues"] = conn.execute(
            "SELECT COUNT(*) FROM pipeline_issue "
            "WHERE code='ValueError' AND message LIKE 'SHA256 mismatch%'"
        ).fetchone()[0]
        checks["candidate_status"] = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT status,COUNT(*) FROM semantic_candidate GROUP BY status"
            )
        }
        checks["candidate_levels"] = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT promotion_level,COUNT(*) "
                "FROM semantic_candidate GROUP BY promotion_level"
            )
        }
        checks["tables"] = {
            name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in [
                "symbol_universe",
                "issuer",
                "security",
                "filing",
                "filing_document",
                "filing_section",
                "filing_table",
                "xbrl_fact",
                "form13f_holding",
                "event_ledger",
                "evidence_snippet",
                "section_semantic_context",
                "semantic_candidate",
                "semantic_review",
                "semantic_assertion",
                "company_relation",
            ]
        }
    guarded = [
        "ownership_forms",
        "missing_available_at",
        "missing_evidence_time",
        "orphan_assertions",
        "orphan_candidates",
        "accepted_without_promotion",
        "self_target_relations",
        "sha_mismatch_issues",
    ]
    return {
        "passed": (
            checks["quick_check"] == "ok"
            and not any(checks[key] for key in guarded)
        ),
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    require_sec = args.command == "run" and _mode(args) != "structure"
    config = _config(args, require_sec=require_sec)
    store = PipelineStore(config.db_path)
    store.initialize()
    if args.command == "init":
        print(config.db_path)
        return 0
    if args.command == "review-export":
        report = export_review_queue(
            store,
            args.output,
            limit=args.limit,
            statuses=(
                tuple(dict.fromkeys(args.status))
                if args.status
                else None
            ),
            levels=(
                tuple(dict.fromkeys(args.level))
                if args.level
                else None
            ),
            include_reviewed=args.include_reviewed,
            dedupe_evidence=not args.no_dedupe_evidence,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.command == "review-import":
        report = import_review_decisions(
            store,
            args.input,
            reviewer_type=args.reviewer_type,
            reviewer_id=args.reviewer_id,
            reviewer_version=args.reviewer_version,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if not report["errors"] else 2
    pipeline = DagPipeline(config, store=store, mode=_mode(args))
    if args.command == "run":
        if args.rebuild_semantic and _mode(args) != "structure":
            raise SystemExit(
                "--rebuild-semantic is only valid with --mode structure"
            )
        run_id = pipeline.create_online_run(
            metadata_path=args.metadata,
            limit=args.limit,
            refresh=args.refresh,
            use_yahoo=not args.no_yahoo,
            rebuild_semantic=args.rebuild_semantic,
        )
        print(json.dumps(pipeline.run(run_id), ensure_ascii=False, indent=2))
        return 0
    if args.command == "import-archive":
        run_id = pipeline.create_archive_run(args.archives, symbol=args.symbol)
        print(json.dumps(pipeline.run(run_id), ensure_ascii=False, indent=2))
        return 0
    if args.command == "resume":
        print(json.dumps(pipeline.run(args.run_id), ensure_ascii=False, indent=2))
        return 0
    if args.command == "status":
        run = store.query(
            "SELECT * FROM pipeline_run WHERE run_id=?",
            (args.run_id,),
        )
        print(
            json.dumps(
                {"run": run, "tasks": store.task_counts(args.run_id)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if run else 1
    if args.command == "validate":
        report = validate_database(store)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        print(text)
        return 0 if report["passed"] else 2
    if args.command == "inspect":
        symbol = args.symbol.upper()
        output = {
            "security": store.query(
                "SELECT s.*,i.* FROM security s "
                "JOIN issuer i ON i.issuer_id=s.issuer_id "
                "WHERE s.symbol=?",
                (symbol,),
            ),
            "filings": store.query(
                "SELECT accession,form,available_at,status "
                "FROM security_filing WHERE query_symbol=? "
                "ORDER BY available_at DESC",
                (symbol,),
            ),
            "assertions": store.query(
                """SELECT predicate,object_json,available_at,confidence,status
                   FROM security_semantic_assertion
                   WHERE query_symbol=?
                   ORDER BY available_at DESC LIMIT 100""",
                (symbol,),
            ),
            "candidates": store.query(
                """SELECT c.predicate,c.object_json,c.available_at,
                          c.confidence,c.status,c.promotion_level,
                          c.section_role
                   FROM semantic_candidate c
                   JOIN security s ON s.issuer_id=c.issuer_id
                   WHERE s.symbol=?
                   ORDER BY c.available_at DESC LIMIT 100""",
                (symbol,),
            ),
            "relations": store.query(
                """SELECT target_entity_key,target_ticker,relation_type,
                          available_at,confidence,status
                   FROM security_company_relation
                   WHERE query_symbol=?
                   ORDER BY available_at DESC LIMIT 100""",
                (symbol,),
            ),
            "events": store.query(
                """SELECT event_type,item,event_time,title
                   FROM security_event_ledger
                   WHERE query_symbol=?
                   ORDER BY event_time DESC LIMIT 100""",
                (symbol,),
            ),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if output["security"] else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
