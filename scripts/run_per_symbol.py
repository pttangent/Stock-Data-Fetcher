#!/usr/bin/env python3
"""Run SEC pipeline with per-symbol SQLite databases.

Simple serial execution with a concurrency limit. Uses subprocess.Popen
+ poll() to manage slots without spawning extra worker processes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd


def run_symbol(
    symbol: str,
    *,
    config_path: str,
    base_db_dir: Path,
    base_data_dir: Path,
    metadata_path: str,
    mode: str = "all",
    sec_identity: str | None = None,
    sec_rps: float = 0.8,
    max_filings: int | None = 200,
    from_date: str | None = None,
    to_date: str | None = None,
) -> subprocess.Popen:
    """Start a pipeline run for a single symbol."""

    symbol_upper = symbol.upper()
    db_dir = base_db_dir / symbol_upper[0] / symbol_upper
    data_dir = base_data_dir / symbol_upper[0] / symbol_upper
    db_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    db_path = db_dir / f"{symbol_upper}.db"

    # Build config override - single worker per symbol since we parallelize at symbol level
    cfg: dict[str, Any] = {
        "db_path": str(db_path),
        "data_dir": str(data_dir),
        "symbol_metadata_path": str(metadata_path),
        "sec_requests_per_second": sec_rps,
        "workers": {
            "download": 1,
            "yahoo": 1,
            "parse_core": 1,
            "parse_event": 1,
            "parse_holdings": 1,
            "parse_other": 1,
            "semantic_core": 1,
            "semantic_event": 1,
            "semantic_holdings": 1,
            "semantic_other": 1,
            "finalize": 1,
        },
    }
    if max_filings is not None:
        cfg["max_filings_per_symbol"] = max_filings
    if from_date:
        cfg["from_date"] = from_date
    if to_date:
        cfg["to_date"] = to_date

    tmp_config = db_dir / "config.json"
    tmp_config.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    # Create single-symbol metadata parquet
    meta_df = pd.read_parquet(metadata_path)
    symbol_row = meta_df[meta_df["symbol"] == symbol_upper]
    if symbol_row.empty:
        raise ValueError(f"Symbol {symbol_upper} not found in metadata")
    symbol_meta_path = db_dir / "symbol.parquet"
    symbol_row.to_parquet(symbol_meta_path, index=False)

    # Build command - use venv python
    script_dir = Path(__file__).parent.parent
    venv_python = script_dir / ".venv/Scripts/python.exe"
    python_exe = str(venv_python) if venv_python.exists() else sys.executable

    cmd = [
        python_exe, "-m", "equity_semantic_library.sec_pipeline.cli",
        "--config", str(config_path),
        "--db", str(db_path),
        "--data-dir", str(data_dir),
        "run",
        "--metadata", str(symbol_meta_path),
        "--mode", mode,
        "--max-workers", "1",
    ]

    env = os.environ.copy()
    if sec_identity:
        env["SEC_IDENTITY"] = sec_identity

    log_path = db_dir / "run.log"
    err_path = db_dir / "run.err"
    out = open(log_path, "a", encoding="utf-8")
    err = open(err_path, "a", encoding="utf-8")

    return subprocess.Popen(cmd, stdout=out, stderr=err, env=env)


def symbol_done(db_path: Path) -> bool:
    """Check if a symbol's pipeline has completed."""
    if not db_path.exists():
        return False
    import sqlite3
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA query_only=ON")
        pending = conn.execute(
            "SELECT COUNT(*) FROM dag_task WHERE status IN ('pending','running')"
        ).fetchone()[0]
        conn.close()
        return pending == 0
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Run per-symbol SEC pipeline")
    parser.add_argument("--config", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--db-dir", default="data/symbols")
    parser.add_argument("--data-dir", default="data/symbol_data")
    parser.add_argument("--mode", default="all", choices=["all", "download", "structure"])
    parser.add_argument("--symbols", help="Comma-separated (default: all from metadata)")
    parser.add_argument("--max-concurrent", type=int, default=24, help="Max concurrent symbol processes")
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    parser.add_argument("--max-filings", type=int, default=200)
    parser.add_argument("--sec-rps", type=float, default=0.8)
    args = parser.parse_args()

    sec_identity = os.getenv("SEC_IDENTITY") or os.getenv("SEC_USER_AGENT") or "Stock-Data-Fetcher pigtop212@gmail.com"
    os.environ["SEC_IDENTITY"] = sec_identity

    # Load symbols
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        df = pd.read_parquet(args.metadata)
        symbols = df[df.get("is_etf", False) != True]["symbol"].tolist()

    print(f"Symbols: {len(symbols)} | Max concurrent: {args.max_concurrent} | Mode: {args.mode}")

    base_db_dir = Path(args.db_dir)
    base_data_dir = Path(args.data_dir)

    running: dict[str, subprocess.Popen] = {}
    completed: set[str] = set()
    failed: set[str] = set()

    for symbol in symbols:
        if symbol in completed or symbol in failed:
            continue

        # Wait for a free slot
        while len(running) >= args.max_concurrent:
            for sym in list(running):
                proc = running[sym]
                if proc.poll() is not None:
                    del running[sym]
                    db_path = base_db_dir / sym[0] / sym / f"{sym}.db"
                    if proc.returncode == 0 or symbol_done(db_path):
                        completed.add(sym)
                        print(f"OK {sym} completed [{len(completed)}/{len(symbols)}]")
                    else:
                        failed.add(sym)
                        print(f"FAIL {sym} failed (exit {proc.returncode})")
            time.sleep(2)

        # Start new symbol
        try:
            proc = run_symbol(
                symbol,
                config_path=args.config,
                base_db_dir=base_db_dir,
                base_data_dir=base_data_dir,
                metadata_path=args.metadata,
                mode=args.mode,
                sec_identity=sec_identity,
                sec_rps=args.sec_rps,
                max_filings=args.max_filings,
                from_date=args.from_date,
                to_date=args.to_date,
            )
            running[symbol] = proc
        except Exception as exc:
            failed.add(symbol)
            print(f"FAIL {symbol} start failed: {exc}")

    # Wait for remaining
    while running:
        for sym in list(running):
            proc = running[sym]
            if proc.poll() is not None:
                del running[sym]
                db_path = base_db_dir / sym[0] / sym / f"{sym}.db"
                if proc.returncode == 0 or symbol_done(db_path):
                    completed.add(sym)
                    print(f"OK {sym} completed [{len(completed)}/{len(symbols)}]")
                else:
                    failed.add(sym)
                    print(f"FAIL {sym} failed (exit {proc.returncode})")
        if running:
            time.sleep(2)

    print(f"\nDone: {len(completed)} completed, {len(failed)} failed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
