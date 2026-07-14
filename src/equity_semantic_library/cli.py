from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from .config import Settings
from .db import Database
from .pipeline import IngestionPipeline, load_symbols
from .validation import validate_database


def _settings(args: argparse.Namespace, require_sec: bool = False) -> Settings:
    base = Settings.from_env(require_sec_identity=require_sec)
    return Settings(
        db_path=Path(args.db or base.db_path),
        data_dir=Path(args.data_dir or base.data_dir),
        sec_identity=base.sec_identity,
        sec_requests_per_second=base.sec_requests_per_second,
        sec_max_attempts=base.sec_max_attempts,
        sec_cache_ttl_hours=base.sec_cache_ttl_hours,
        yf_min_interval_seconds=base.yf_min_interval_seconds,
        yf_max_attempts=base.yf_max_attempts,
        yf_cache_ttl_hours=base.yf_cache_ttl_hours,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="esl", description="Equity Semantic Library")
    parser.add_argument("--db", help="SQLite database path")
    parser.add_argument("--data-dir", help="Raw/cache data directory")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize the database schema")

    bootstrap = sub.add_parser(
        "bootstrap-sec", help="Download SEC ticker map and optional bulk submissions"
    )
    bootstrap.add_argument("--bulk-submissions", action="store_true")
    bootstrap.add_argument("--refresh", action="store_true")

    ingest = sub.add_parser("ingest", help="Ingest one or more symbols")
    ingest.add_argument("symbols", nargs="+")
    ingest.add_argument("--no-sec", action="store_true")
    ingest.add_argument("--no-yahoo", action="store_true")
    ingest.add_argument("--refresh", action="store_true")

    ingest_file = sub.add_parser("ingest-file", help="Ingest symbols from CSV/TXT/JSON/Parquet")
    ingest_file.add_argument("path")
    ingest_file.add_argument("--symbol-column", default="symbol")
    ingest_file.add_argument("--limit", type=int)
    ingest_file.add_argument("--no-sec", action="store_true")
    ingest_file.add_argument("--no-yahoo", action="store_true")
    ingest_file.add_argument("--refresh", action="store_true")

    validate = sub.add_parser("validate", help="Run release checks")
    validate.add_argument("--output")

    inspect = sub.add_parser("inspect", help="Inspect one symbol")
    inspect.add_argument("symbol")

    export = sub.add_parser("export", help="Export a table to CSV")
    export.add_argument(
        "table",
        choices=[
            "issuer",
            "security",
            "source_record",
            "company_profile_snapshot",
            "source_document",
            "filing_section",
            "ingestion_error",
            "work_queue",
        ],
    )
    export.add_argument("output")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    require_sec = args.command == "bootstrap-sec" or (
        args.command in {"ingest", "ingest-file"} and not args.no_sec
    )
    settings = _settings(args, require_sec=require_sec)
    database = Database(settings.db_path)

    if args.command == "init":
        database.initialize()
        print(settings.db_path)
        return 0

    if args.command == "bootstrap-sec":
        from .providers.sec import SecProvider

        provider = SecProvider(settings)
        provider.load_ticker_map(refresh=args.refresh)
        if args.bulk_submissions:
            provider.bootstrap_bulk_submissions(refresh=args.refresh)
        print(settings.cache_dir / "sec")
        return 0

    if args.command in {"ingest", "ingest-file"}:
        pipeline = IngestionPipeline(settings, database=database)
        pipeline.initialize()
        symbols = (
            args.symbols
            if args.command == "ingest"
            else load_symbols(args.path, args.symbol_column)
        )
        if getattr(args, "limit", None):
            symbols = symbols[: args.limit]
        if not symbols:
            parser.error("No symbols to ingest")
        if args.no_sec and args.no_yahoo:
            parser.error("At least one source must be enabled")
        run_id = pipeline.ingest(
            symbols,
            use_sec=not args.no_sec,
            use_yahoo=not args.no_yahoo,
            refresh=args.refresh,
        )
        print(run_id)
        return 0

    if args.command == "validate":
        database.initialize()
        report = validate_database(database)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        print(text)
        return 0 if report["passed"] else 2

    if args.command == "inspect":
        rows = database.query(
            """
            SELECT s.*, i.cik, i.legal_name, i.identity_status
            FROM security s JOIN issuer i ON i.issuer_id=s.issuer_id
            WHERE s.symbol=?
            """,
            (args.symbol.upper(),),
        )
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0 if rows else 1

    if args.command == "export":
        rows = database.query(f"SELECT * FROM {args.table}")
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        if rows:
            with output.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        else:
            output.write_text("", encoding="utf-8")
        print(output)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
