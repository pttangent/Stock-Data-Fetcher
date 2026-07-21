"""Preview SEC filing counts and split symbols into normal vs heavy batches.

Runs a lightweight SEC discovery pass (no raw downloads) to count how many
filings each symbol has in the configured date range. Symbols above the
threshold are moved into separate "heavy" batches so normal batches finish
quickly.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

from equity_semantic_library.sec_pipeline.archive_source import GlobalRateGate, SecArchive, SecClient
from equity_semantic_library.sec_pipeline.config import PipelineConfig
from equity_semantic_library.sec_pipeline.forms import FormPolicy, form_group


def count_filings(symbol: str, archive: SecArchive, policy: FormPolicy, from_date: str | None, to_date: str | None) -> int:
    match = archive.lookup(symbol)
    if not match:
        return -1
    _, filings = archive.discover_filings(
        match["cik"], policy, refresh=False, from_date=from_date, to_date=to_date
    )
    return sum(
        1
        for f in filings
        if form_group(str(f.get("form") or "").upper()) is not None
    )


def split_batches(
    source_parquet: str | Path,
    output_dir: str | Path,
    config_path: str | Path,
    threshold: int,
    normal_size: int,
    heavy_size: int,
    top_n: int,
) -> tuple[list[Path], list[Path]]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = PipelineConfig.from_json(config_path)
    policy = FormPolicy(config.include_forms, config.exclude_forms)
    gate = GlobalRateGate(config.sec_requests_per_second)
    client = SecClient(config, gate)
    archive = SecArchive(config, client)

    raw = pd.read_parquet(source_parquet)
    df = raw[raw.get("is_etf", False) != True].copy()
    df = (
        df.sort_values("market_cap", ascending=False, na_position="last")
        .head(top_n)
        .reset_index(drop=True)
    )

    normal_rows: list[dict] = []
    heavy_rows: list[dict] = []
    print(f"Previewing {len(df)} symbols with threshold={threshold}...")
    for _, row in df.iterrows():
        symbol = row["symbol"]
        count = count_filings(symbol, archive, policy, config.from_date, config.to_date)
        if count < 0:
            print(f"  {symbol}: no SEC mapping")
            normal_rows.append(dict(row))
        elif count > threshold:
            print(f"  {symbol}: HEAVY ({count} filings)")
            heavy_rows.append({**dict(row), "filing_count": count})
        else:
            print(f"  {symbol}: normal ({count} filings)")
            normal_rows.append({**dict(row), "filing_count": count})

    def write_chunks(rows: list[dict], prefix: str, size: int) -> list[Path]:
        if not rows:
            return []
        written: list[Path] = []
        for i in range(0, len(rows), size):
            chunk = rows[i : i + size]
            batch_num = i // size + 1
            path = output_dir / f"{prefix}_{batch_num:02d}.parquet"
            pd.DataFrame(chunk).to_parquet(path, index=False)
            written.append(path)
            print(f"{path}: {len(chunk)} symbols")
        return written

    normal_paths = write_chunks(normal_rows, "batch", normal_size)
    heavy_paths = write_chunks(heavy_rows, "heavy_batch", heavy_size)
    return normal_paths, heavy_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview filing counts and split batches")
    parser.add_argument(
        "--source",
        default=r"D:\DEV\AnotherNetworkFactory\RAW_DATA\metadata\symbol_metadata.parquet",
        help="Path to symbol_metadata.parquet",
    )
    parser.add_argument("--output-dir", default="data/batches", help="Directory to write batch parquet files")
    parser.add_argument("--config", default="config/sec_pipeline.batch.json", help="Pipeline config JSON")
    parser.add_argument("--threshold", type=int, default=100, help="Max filings for a normal symbol")
    parser.add_argument("--normal-size", type=int, default=40, help="Symbols per normal batch")
    parser.add_argument("--heavy-size", type=int, default=5, help="Symbols per heavy batch")
    parser.add_argument("--top-n", type=int, default=1000, help="Process top N symbols by market cap")
    args = parser.parse_args()

    if not os.getenv("SEC_IDENTITY"):
        raise RuntimeError("SEC_IDENTITY environment variable is required")

    split_batches(
        args.source,
        args.output_dir,
        args.config,
        args.threshold,
        args.normal_size,
        args.heavy_size,
        args.top_n,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
