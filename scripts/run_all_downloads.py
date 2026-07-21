"""Orchestrate download-only runs for all 40-symbol batches.

Keeps up to MAX_CONCURRENT batches running in parallel. Each batch uses its
own SQLite database to avoid lock contention. Intended for the first pass of
the top-1000 SEC pipeline: raw download + Yahoo snapshot only.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

MAX_CONCURRENT = 5
BATCH_SIZE = 40
TOP_N = 1000
SOURCE_PARQUET = r"D:\DEV\AnotherNetworkFactory\RAW_DATA\metadata\symbol_metadata.parquet"
BASE_DIR = Path("data/batches")
REPORTS_DIR = Path("reports")
CONFIG = Path("config/sec_pipeline.batch.json")
VENV_PYTHON = Path(".venv/Scripts/python.exe")
ESL_SEC = Path(".venv/Scripts/esl-sec.exe")


def ensure_batches() -> list[Path]:
    raw = pd.read_parquet(SOURCE_PARQUET)
    df = raw[raw.get("is_etf", False) != True].copy()
    df = (
        df.sort_values("market_cap", ascending=False, na_position="last")
        .head(TOP_N)
        .reset_index(drop=True)
    )
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    parquet_paths: list[Path] = []
    for i in range(0, len(df), BATCH_SIZE):
        batch_num = i // BATCH_SIZE + 1
        batch_df = df.iloc[i : i + BATCH_SIZE].copy()
        path = BASE_DIR / f"batch_{batch_num:02d}.parquet"
        batch_df.to_parquet(path, index=False)
        parquet_paths.append(path)
    return parquet_paths


def db_path(batch_num: int) -> Path:
    return BASE_DIR / f"batch_{batch_num:02d}" / "sec_yfinance_structured.db"


def data_dir(batch_num: int) -> Path:
    return BASE_DIR / f"batch_{batch_num:02d}" / "sec_yfinance"


def init_batch(batch_num: int) -> None:
    if db_path(batch_num).exists():
        return
    subprocess.run(
        [
            str(ESL_SEC),
            "--config", str(CONFIG),
            "--db", str(db_path(batch_num)),
            "--data-dir", str(data_dir(batch_num)),
            "init",
        ],
        check=True,
    )


def start_download(batch_num: int) -> subprocess.Popen:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = open(REPORTS_DIR / f"batch_{batch_num:02d}.log", "a", encoding="utf-8")
    err = open(REPORTS_DIR / f"batch_{batch_num:02d}.err", "a", encoding="utf-8")
    env = os.environ.copy()
    env["SEC_IDENTITY"] = "Stock-Data-Fetcher pigtop212@gmail.com"
    env["SEC_REQUESTS_PER_SECOND"] = "0.8"
    return subprocess.Popen(
        [
            str(ESL_SEC),
            "--config", str(CONFIG),
            "--db", str(db_path(batch_num)),
            "--data-dir", str(data_dir(batch_num)),
            "run", "--mode", "download",
            "--metadata", str(BASE_DIR / f"batch_{batch_num:02d}.parquet"),
        ],
        stdout=out,
        stderr=err,
        env=env,
    )


def batch_done(batch_num: int) -> bool:
    path = db_path(batch_num)
    if not path.exists():
        return False
    import sqlite3
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA query_only=ON")
    run = conn.execute("SELECT status FROM pipeline_run").fetchone()
    pending = conn.execute(
        "SELECT COUNT(*) FROM dag_task WHERE status IN ('pending','running')"
    ).fetchone()[0]
    conn.close()
    return run is not None and pending == 0


def main() -> int:
    ensure_batches()
    parquet_paths = sorted(
        p for p in BASE_DIR.glob("batch_*.parquet")
        if p.stem.startswith("batch_") and p.stem[6:].isdigit()
    )
    total = len(parquet_paths)
    print(f"Total batches: {total}, max concurrent: {MAX_CONCURRENT}")

    running: dict[int, subprocess.Popen] = {}
    completed: set[int] = set()
    failed: set[int] = set()

    for batch_num in range(1, total + 1):
        init_batch(batch_num)

    while len(completed) + len(failed) < total:
        # Clean up finished processes
        for batch_num in list(running):
            proc = running[batch_num]
            if proc.poll() is not None:
                del running[batch_num]
                if proc.returncode == 0 or batch_done(batch_num):
                    completed.add(batch_num)
                    print(f"batch_{batch_num:02d} completed")
                else:
                    failed.add(batch_num)
                    print(f"batch_{batch_num:02d} failed (exit {proc.returncode})")

        # Start new batches up to max concurrent
        while len(running) < MAX_CONCURRENT:
            next_batch = next(
                (b for b in range(1, total + 1) if b not in running and b not in completed and b not in failed),
                None,
            )
            if next_batch is None:
                break
            proc = start_download(next_batch)
            running[next_batch] = proc
            print(f"started batch_{next_batch:02d} (pid {proc.pid})")

        if not running and len(completed) + len(failed) < total:
            time.sleep(5)
            continue

        time.sleep(30)

    print(f"All done. completed={len(completed)} failed={len(failed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
