#!/usr/bin/env python3
"""Re-download symbols with missing raw files using per-symbol pipeline.

Usage:
    python scripts/redownload_missing.py --metadata data/batches/batch_01.parquet --symbols AAPL,ABBV
    python scripts/redownload_missing.py --metadata data/batches/batch_01.parquet --all-missing
"""

from __future__ import annotations

import argparse
import glob
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd


def find_symbols_with_missing_raw(db_dir: str = "data/symbols") -> list[tuple[str, int, int]]:
    """Find all symbols where raw_storage_uri points to missing files."""
    results = []
    base = Path(db_dir)

    for db_path in base.rglob("*.db"):
        if "backup" in db_path.name:
            continue
        sym = db_path.stem
        try:
            conn = sqlite3.connect(str(db_path), timeout=5)
            rows = conn.execute(
                "SELECT accession, raw_storage_uri FROM filing WHERE raw_storage_uri IS NOT NULL"
            ).fetchall()

            missing = 0
            total = len(rows)
            for acc, uri in rows:
                if not os.path.exists(uri):
                    missing += 1

            conn.close()

            if missing > 0:
                results.append((sym, missing, total))
        except Exception:
            pass

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def run_symbol(
    symbol: str,
    config_path: str,
    metadata_path: str,
    base_db_dir: Path,
    base_data_dir: Path,
) -> subprocess.Popen:
    """Start pipeline for a single symbol."""
    symbol_upper = symbol.upper()
    db_dir = base_db_dir / symbol_upper[0] / symbol_upper
    data_dir = base_data_dir / symbol_upper[0] / symbol_upper
    db_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    db_path = db_dir / f"{symbol_upper}.db"

    # Delete old DB to start fresh
    if db_path.exists():
        db_path.unlink()
    for backup in db_dir.glob("*.backup"):
        backup.unlink()

    # Create single-symbol metadata
    meta_df = pd.read_parquet(metadata_path)
    symbol_row = meta_df[meta_df["symbol"] == symbol_upper]
    if symbol_row.empty:
        raise ValueError(f"Symbol {symbol_upper} not found in metadata")
    symbol_meta_path = db_dir / "symbol.parquet"
    symbol_row.to_parquet(symbol_meta_path, index=False)

    # Find batch parquet containing this symbol
    batch_parquet = None
    for i in range(1, 26):
        bp = Path(f"data/batches/batch_{i:02d}.parquet")
        if bp.exists():
            bdf = pd.read_parquet(bp)
            if symbol_upper in bdf["symbol"].values:
                batch_parquet = bp
                break

    # Build command
    script_dir = Path(__file__).parent.parent
    venv_python = script_dir / ".venv/Scripts/python.exe"
    python_exe = str(venv_python) if venv_python.exists() else sys.executable

    cmd = [
        python_exe, "-m", "equity_semantic_library.sec_pipeline.cli",
        "--config", config_path,
        "--db", str(db_path),
        "--data-dir", str(data_dir),
        "run",
        "--metadata", str(symbol_meta_path),
        "--mode", "all",
        "--max-workers", "1",
    ]

    sec_identity = os.getenv("SEC_IDENTITY") or os.getenv("SEC_USER_AGENT") or "Stock-Data-Fetcher pigtop212@gmail.com"
    env = os.environ.copy()
    env["SEC_IDENTITY"] = sec_identity

    log_path = db_dir / "run.log"
    err_path = db_dir / "run.err"
    out = open(log_path, "a", encoding="utf-8")
    err = open(err_path, "a", encoding="utf-8")

    return subprocess.Popen(cmd, stdout=out, stderr=err, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-download symbols with missing raw files")
    parser.add_argument("--config", default="config/sec_pipeline.batch.json", help="Pipeline config")
    parser.add_argument("--db-dir", default="data/symbols", help="Per-symbol DB directory")
    parser.add_argument("--data-dir", default="data/symbol_data", help="Per-symbol data directory")
    parser.add_argument("--symbols", help="Comma-separated symbols to re-download")
    parser.add_argument("--all-missing", action="store_true", help="Re-download all symbols with missing raw files")
    parser.add_argument("--max-concurrent", type=int, default=8, help="Max concurrent downloads")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be re-downloaded")
    args = parser.parse_args()

    if args.all_missing:
        missing = find_symbols_with_missing_raw(args.db_dir)
        symbols = [s for s, _, _ in missing]
        print(f"Found {len(symbols)} symbols with missing raw files")
        for sym, miss, total in missing[:20]:
            print(f"  {sym:6} | missing {miss}/{total}")
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more")
    elif args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        print("Error: specify --symbols or --all-missing")
        return 1

    if args.dry_run:
        print(f"\nDry run: would re-download {len(symbols)} symbols")
        return 0

    print(f"\nRe-downloading {len(symbols)} symbols...")
    print(f"Max concurrent: {args.max_concurrent}")

    base_db_dir = Path(args.db_dir)
    base_data_dir = Path(args.data_dir)

    running: dict[str, subprocess.Popen] = {}
    completed: set[str] = set()
    failed: set[str] = set()

    for symbol in symbols:
        if symbol in completed or symbol in failed:
            continue

        # Wait for free slot
        while len(running) >= args.max_concurrent:
            for sym in list(running):
                proc = running[sym]
                if proc.poll() is not None:
                    del running[sym]
                    if proc.returncode == 0:
                        completed.add(sym)
                        print(f"OK {sym} completed [{len(completed)}/{len(symbols)}]")
                    else:
                        failed.add(sym)
                        print(f"FAIL {sym} failed (exit {proc.returncode})")
            time.sleep(2)

        # Start new symbol
        try:
            # Find metadata parquet for this symbol
            metadata_path = None
            for i in range(1, 26):
                bp = Path(f"data/batches/batch_{i:02d}.parquet")
                if bp.exists():
                    bdf = pd.read_parquet(bp)
                    if symbol in bdf["symbol"].values:
                        metadata_path = str(bp)
                        break

            if not metadata_path:
                print(f"FAIL {symbol}: not found in any batch parquet")
                failed.add(symbol)
                continue

            proc = run_symbol(
                symbol,
                config_path=args.config,
                metadata_path=metadata_path,
                base_db_dir=base_db_dir,
                base_data_dir=base_data_dir,
            )
            running[symbol] = proc
            print(f"START {symbol} [{len(running)} running]")
        except Exception as exc:
            failed.add(symbol)
            print(f"FAIL {symbol} start failed: {exc}")

    # Wait for remaining
    while running:
        for sym in list(running):
            proc = running[sym]
            if proc.poll() is not None:
                del running[sym]
                if proc.returncode == 0:
                    completed.add(sym)
                    print(f"OK {sym} completed [{len(completed)}/{len(symbols)}]")
                else:
                    failed.add(sym)
                    print(f"FAIL {sym} failed (exit {proc.returncode})")
        if running:
            time.sleep(2)

    print(f"\nDone: {len(completed)} completed, {len(failed)} failed")
    if failed:
        print(f"Failed: {', '.join(sorted(failed))}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
