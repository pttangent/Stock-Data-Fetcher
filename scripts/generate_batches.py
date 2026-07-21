"""Generate per-batch symbol metadata parquet files for the SEC pipeline.

Splits the top 1000 non-ETF symbols by market cap into fixed-size batches
(default 40). Each batch gets its own parquet so the pipeline can run with
independent databases and avoid SQLite lock contention.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def generate_batches(
    source_parquet: str | Path,
    output_dir: str | Path,
    batch_size: int = 40,
    top_n: int = 1000,
) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw = pd.read_parquet(source_parquet)
    df = raw[raw.get("is_etf", False) != True].copy()
    df = (
        df.sort_values("market_cap", ascending=False, na_position="last")
        .head(top_n)
        .reset_index(drop=True)
    )

    written: list[Path] = []
    for i in range(0, len(df), batch_size):
        batch_num = i // batch_size + 1
        batch_df = df.iloc[i : i + batch_size].copy()
        path = output_dir / f"batch_{batch_num:02d}.parquet"
        batch_df.to_parquet(path, index=False)
        written.append(path)
        print(
            f"{path}: {len(batch_df)} symbols, "
            f"first={batch_df.iloc[0]['symbol']}, last={batch_df.iloc[-1]['symbol']}"
        )
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate batch parquet files")
    parser.add_argument(
        "--source",
        default=r"D:\DEV\AnotherNetworkFactory\RAW_DATA\metadata\symbol_metadata.parquet",
        help="Path to symbol_metadata.parquet",
    )
    parser.add_argument(
        "--output-dir",
        default="data/batches",
        help="Directory to write batch parquet files",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=40,
        help="Number of symbols per batch",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=1000,
        help="Process top N symbols by market cap",
    )
    args = parser.parse_args()
    generate_batches(args.source, args.output_dir, args.batch_size, args.top_n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
