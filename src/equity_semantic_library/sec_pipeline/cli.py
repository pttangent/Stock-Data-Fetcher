from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .config import PipelineConfig
from .dag import DagPipeline
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
    config = PipelineConfig.from_json(args.config, **overrides) if getattr(args, "config", None) else PipelineConfig.from_env(**overrides)
    config.validate(require_sec=require_sec)
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="esl-sec", description="Multi-worker SEC/Yfinance DAG pipeline")
    parser.add_argument("--config", help="JSON pipeline configuration")
    parser.add_argument("--db", help="Separate pipeline SQLite database path")
    parser.add_argument("--data-dir", help="Raw/cache/run data directory")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Initialize the separate pipeline database")
    run = sub.add_parser("run", help="Read symbol metadata and run the full online pipeline")
    run.add_argument("--metadata", help="Read-only symbol_metadata.parquet or CSV")
    run.add_argument("--limit", type=int)
    run.add_argument("--from-date", help="Filing date lower bound YYYY-MM-DD")
    run.add_argument("--to-date", help="Filing date upper bound YYYY-MM-DD")
    run.add_argument("--refresh", action="store_true")
    run.add_argument("--no-yahoo", action="store_true")
    archive = sub.add_parser("import-archive", help="Run deterministic structure/semantic workers on existing ticker ZIP archives")
    archive.add_argument("archives", nargs="+")
    archive.add_argument("--symbol", help="Fallback symbol when archive metadata lacks ticker")
    resume = sub.add_parser("resume", help="Resume a persistent DAG run")
    resume.add_argument("run_id")
    status = sub.add_parser("status", help="Show a run and task counts")
    status.add_argument("run_id")
    validate = sub.add_parser("validate", help="Run database governance checks")
    validate.add_argument("--output")
    inspect = sub.add_parser("inspect", help="Inspect structured output for one symbol")
    inspect.add_argument("symbol")
    return parser


def validate_database(store: PipelineStore) -> dict:
    checks = {}
    with store.connect() as conn:
        checks["quick_check"] = conn.execute("PRAGMA quick_check").fetchone()[0]
        checks["ownership_forms"] = conn.execute("SELECT COUNT(*) FROM filing WHERE base_form IN ('3','4','5','144')").fetchone()[0]
        checks["missing_available_at"] = conn.execute("SELECT COUNT(*) FROM filing WHERE available_at IS NULL OR available_at='' ").fetchone()[0]
        checks["missing_evidence_time"] = conn.execute("SELECT COUNT(*) FROM evidence_snippet WHERE available_at IS NULL OR observed_at IS NULL").fetchone()[0]
        checks["orphan_assertions"] = conn.execute("SELECT COUNT(*) FROM semantic_assertion a LEFT JOIN evidence_snippet e ON e.evidence_id=a.evidence_id WHERE e.evidence_id IS NULL").fetchone()[0]
        checks["sha_mismatch_issues"] = conn.execute("SELECT COUNT(*) FROM pipeline_issue WHERE code='ValueError' AND message LIKE 'SHA256 mismatch%'").fetchone()[0]
        checks["tables"] = {name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in [
            "symbol_universe", "issuer", "security", "filing", "filing_document", "filing_section", "filing_table",
            "xbrl_fact", "form13f_holding", "event_ledger", "evidence_snippet", "semantic_assertion", "company_relation",
        ]}
    guarded = ["ownership_forms", "missing_available_at", "missing_evidence_time", "orphan_assertions", "sha_mismatch_issues"]
    return {"passed": checks["quick_check"] == "ok" and not any(checks[key] for key in guarded), "checks": checks}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = _config(args, require_sec=args.command == "run")
    store = PipelineStore(config.db_path)
    store.initialize()
    if args.command == "init":
        print(config.db_path)
        return 0
    pipeline = DagPipeline(config, store=store)
    if args.command == "run":
        run_id = pipeline.create_online_run(metadata_path=args.metadata, limit=args.limit, refresh=args.refresh, use_yahoo=not args.no_yahoo)
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
        run = store.query("SELECT * FROM pipeline_run WHERE run_id=?", (args.run_id,))
        print(json.dumps({"run": run, "tasks": store.task_counts(args.run_id)}, ensure_ascii=False, indent=2))
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
            "security": store.query("SELECT s.*,i.* FROM security s JOIN issuer i ON i.issuer_id=s.issuer_id WHERE s.symbol=?", (symbol,)),
            "filings": store.query("SELECT accession,form,available_at,status FROM filing WHERE symbol=? ORDER BY available_at DESC", (symbol,)),
            "topics": store.query("SELECT predicate,object_json,available_at,confidence,status FROM semantic_assertion a JOIN filing f ON f.filing_id=a.filing_id WHERE f.symbol=? ORDER BY available_at DESC LIMIT 100", (symbol,)),
            "relations": store.query("SELECT target_entity_key,target_ticker,relation_type,available_at,confidence,status FROM company_relation r JOIN filing f ON f.filing_id=r.filing_id WHERE f.symbol=? ORDER BY available_at DESC LIMIT 100", (symbol,)),
            "events": store.query("SELECT event_type,item,event_time,title FROM event_ledger WHERE symbol=? ORDER BY event_time DESC LIMIT 100", (symbol,)),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if output["security"] else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
