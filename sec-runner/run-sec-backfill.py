#!/usr/bin/env python3
"""Sequential SEC backfill wrapper with per-ticker dry-run space check.

Rules:
- Process tickers.txt in order (must be pre-sorted by market cap descending).
- For each ticker, dry-run first to get recommendedFreeBytes.
- Only start actual download if D: free space >= 5 GiB + recommendedFreeBytes * 1.2.
- Run exactly one ticker at a time (no parallel SEC downloads).
- Stop gracefully when space threshold is reached.

Required environment variable:
  SEC_USER_AGENT="Stock-Data-Fetcher <your-real-email@example.com>"
"""

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Configuration
REPO_DIR = Path("D:/DEV/USTOCK/SEC/Stock-Data-Fetcher")
OUTPUT_DIR = Path("D:/SEC_WAREHOUSE")
TICKERS_FILE = Path("D:/DEV/USTOCK/SEC/tickers.txt")
TICKER_CIK_FILE = Path("D:/DEV/USTOCK/SEC/ticker-cik.json")
LOG_FILE = Path("D:/DEV/USTOCK/SEC/backfill-progress.log")
STOP_FREE_GB = 5.0
SAFETY_MARGIN = 1.2
PNPM_CMD = "pnpm.cmd" if sys.platform == "win32" else "pnpm"
DEFAULT_MAX_TICKERS = 0  # 0 = unlimited


def get_free_space_gb(path: Path) -> float:
    usage = shutil.disk_usage(str(path))
    return usage.free / (1024 ** 3)


def run_command(args: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        args,
        cwd=REPO_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr if proc.stderr else ""


def parse_inventory_recommended_bytes(ticker: str, cik: str) -> int | None:
    inv_path = OUTPUT_DIR / f"ticker={ticker}" / f"cik={cik.zfill(10)}" / "inventory.json"
    if not inv_path.exists():
        return None
    try:
        with open(inv_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return int(data.get("recommendedFreeBytes", 0))
    except Exception as e:
        print(f"[WARN] Failed to parse inventory for {ticker}: {e}")
        return None


def parse_run_summary(ticker: str, cik: str) -> dict:
    summary_path = OUTPUT_DIR / f"ticker={ticker}" / f"cik={cik.zfill(10)}" / "run-summary.json"
    if not summary_path.exists():
        return {}
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def is_ticker_complete(summary: dict) -> bool:
    if not summary or not summary.get("completedAt"):
        return False
    selected = summary.get("selectedFilings", 0)
    downloaded = summary.get("downloadedFiles", 0)
    skipped = summary.get("skippedFiles", 0)
    failed = summary.get("failedFiles", 0)
    return failed == 0 and (downloaded + skipped) >= selected


def log_line(line: str) -> None:
    timestamp = datetime.now().isoformat()
    msg = f"[{timestamp}] {line}"
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def main() -> int:
    env = os.environ.copy()
    user_agent = env.get("SEC_USER_AGENT", "").strip()
    if not user_agent or "@" not in user_agent:
        log_line("ERROR: SEC_USER_AGENT environment variable with contact email is required")
        return 1

    max_tickers = DEFAULT_MAX_TICKERS
    if "--max-tickers" in sys.argv:
        i = sys.argv.index("--max-tickers")
        try:
            max_tickers = int(sys.argv[i + 1])
        except (IndexError, ValueError):
            log_line("ERROR: --max-tickers requires a positive integer")
            return 1

    if not TICKERS_FILE.exists():
        log_line(f"ERROR: tickers file not found: {TICKERS_FILE}")
        return 1
    if not TICKER_CIK_FILE.exists():
        log_line(f"ERROR: ticker-cik file not found: {TICKER_CIK_FILE}")
        return 1

    with open(TICKERS_FILE, "r", encoding="utf-8") as f:
        tickers = [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]

    with open(TICKER_CIK_FILE, "r", encoding="utf-8") as f:
        ticker_cik = json.load(f)

    log_line(f"Starting sequential SEC backfill for {len(tickers)} tickers")
    log_line(f"Output: {OUTPUT_DIR}, stop when free space <= {STOP_FREE_GB} GiB")

    completed = 0
    failed = 0
    skipped = 0
    processed_this_run = 0
    completed_ciks: set[str] = set()

    for idx, ticker in enumerate(tickers, start=1):
        cik = ticker_cik.get(ticker)
        if not cik:
            log_line(f"[{idx}/{len(tickers)}] {ticker}: no CIK mapping, skipping")
            skipped += 1
            continue

        summary = parse_run_summary(ticker, cik)
        if is_ticker_complete(summary):
            log_line(
                f"[{idx}/{len(tickers)}] {ticker}: already complete "
                f"(discovered={summary.get('discoveredFilings', 'N/A')} "
                f"selected={summary.get('selectedFilings', 'N/A')} "
                f"downloaded={summary.get('downloadedFiles', 'N/A')} "
                f"skipped={summary.get('skippedFiles', 'N/A')}), skipping"
            )
            completed += 1
            completed_ciks.add(cik)
            continue

        if cik in completed_ciks:
            log_line(f"[{idx}/{len(tickers)}] {ticker}: CIK {cik} already covered by earlier ticker, skipping")
            skipped += 1
            continue

        if max_tickers > 0 and processed_this_run >= max_tickers:
            log_line(f"BATCH LIMIT: processed {processed_this_run} tickers this run, stopping for next batch")
            break
        processed_this_run += 1

        free_gb = get_free_space_gb(OUTPUT_DIR)
        log_line(f"[{idx}/{len(tickers)}] {ticker} CIK {cik}: free space = {free_gb:.2f} GiB")

        if free_gb <= STOP_FREE_GB:
            log_line(f"STOP: free space {free_gb:.2f} GiB <= threshold {STOP_FREE_GB} GiB")
            break

        # Dry-run to estimate space
        dry_args = [
            PNPM_CMD, "--filter", "@workspace/scripts", "sec:backfill", "--",
            "--ticker", ticker,
            "--cik", cik,
            "--ticker-cik-file", str(TICKER_CIK_FILE),
            "--forms", "core",
            "--documents", "both",
            "--from", "2026-01-01",
            "--to", "2026-07-21",
            "--dry-run",
            "--output", str(OUTPUT_DIR),
        ]
        log_line(f"[{idx}/{len(tickers)}] {ticker}: dry-run start")
        rc, out, err = run_command(dry_args, env)
        log_line(f"[{idx}/{len(tickers)}] {ticker}: dry-run exit code {rc}")
        if rc != 0:
            log_line(f"DRY-RUN FAILED for {ticker}; output:\n{out}")
            failed += 1
            continue

        recommended_bytes = parse_inventory_recommended_bytes(ticker, cik)
        if recommended_bytes is None:
            log_line(f"[{idx}/{len(tickers)}] {ticker}: could not read inventory, skipping")
            skipped += 1
            continue

        recommended_gb = recommended_bytes / (1024 ** 3)
        required_gb = STOP_FREE_GB + recommended_gb * SAFETY_MARGIN
        log_line(f"[{idx}/{len(tickers)}] {ticker}: estimated need = {recommended_gb:.2f} GiB, required free = {required_gb:.2f} GiB")

        if free_gb < required_gb:
            log_line(f"STOP: free space {free_gb:.2f} GiB < required {required_gb:.2f} GiB for {ticker}")
            break

        # Actual download
        actual_args = [
            PNPM_CMD, "--filter", "@workspace/scripts", "sec:backfill", "--",
            "--ticker", ticker,
            "--cik", cik,
            "--ticker-cik-file", str(TICKER_CIK_FILE),
            "--forms", "core",
            "--documents", "both",
            "--from", "2026-01-01",
            "--to", "2026-07-21",
            "--order", "newest",
            "--output", str(OUTPUT_DIR),
        ]
        log_line(f"[{idx}/{len(tickers)}] {ticker}: actual download start")
        rc, out, err = run_command(actual_args, env)
        log_line(f"[{idx}/{len(tickers)}] {ticker}: actual download exit code {rc}")

        if rc == 0:
            summary = parse_run_summary(ticker, cik)
            log_line(
                f"[{idx}/{len(tickers)}] {ticker}: OK "
                f"discovered={summary.get('discoveredFilings', 'N/A')} "
                f"selected={summary.get('selectedFilings', 'N/A')} "
                f"downloaded={summary.get('downloadedFiles', 'N/A')} "
                f"skipped={summary.get('skippedFiles', 'N/A')} "
                f"failed={summary.get('failedFiles', 'N/A')}"
            )
            completed += 1
            if is_ticker_complete(summary):
                completed_ciks.add(cik)
        elif rc == 2:
            summary = parse_run_summary(ticker, cik)
            log_line(
                f"[{idx}/{len(tickers)}] {ticker}: PARTIAL "
                f"discovered={summary.get('discoveredFilings', 'N/A')} "
                f"selected={summary.get('selectedFilings', 'N/A')} "
                f"downloaded={summary.get('downloadedFiles', 'N/A')} "
                f"skipped={summary.get('skippedFiles', 'N/A')} "
                f"failed={summary.get('failedFiles', 'N/A')}"
            )
            log_line(f"PARTIAL output for {ticker}:\n{out}")
            failed += 1
        else:
            log_line(f"FAILED output for {ticker}:\n{out}")
            failed += 1

        # Brief pause between tickers to keep SEC polite
        time.sleep(2)

    final_free_gb = get_free_space_gb(OUTPUT_DIR)
    log_line(
        f"DONE: completed={completed}, failed={failed}, skipped={skipped}, "
        f"final free space = {final_free_gb:.2f} GiB"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
