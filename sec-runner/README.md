# SEC Backfill Runner

Sequential SEC full-history backfill runner for `pttangent/Stock-Data-Fetcher`.

## Scope

- **Forms**: `core` — 10-K, 10-Q, 8-K, 20-F, 40-F, 6-K
- **Documents**: `both` — complete submission (`complete-submission.txt`) + primary document (`primary-document.*`)
- **Date range**: `2026-01-01` to `2026-07-21`
- **Order**: `newest` (latest filings first)
- **Ticker source**: `D:\DEV\USTOCK\SEC\tickers.txt` sorted by market cap descending
- **CIK mapping**: `D:\DEV\USTOCK\SEC\ticker-cik.json`
- **Output**: `D:\SEC_WAREHOUSE`
- **Stop condition**: D: free space <= 5 GiB

## Requirements

- Windows with PowerShell
- Node.js 22+
- pnpm 9+
- Python 3.14+ (for the runner wrapper)
- `tickers.txt` and `ticker-cik.json` in `D:\DEV\USTOCK\SEC\`

## Setup

```powershell
# 1. Clone and switch branch
git clone -b agent/sec-evidence-chain https://github.com/pttangent/Stock-Data-Fetcher.git
cd Stock-Data-Fetcher

# 2. Install dependencies
pnpm install --frozen-lockfile

# 3. Set SEC User-Agent (must contain a real contact email)
$env:SEC_USER_AGENT = "Stock-Data-Fetcher <your-real-email@example.com>"
```

## Run

### Option A: Detached loop (recommended for long runs)

```powershell
$env:SEC_USER_AGENT = "Stock-Data-Fetcher <your-real-email@example.com>"
powershell -ExecutionPolicy Bypass -File .\sec-runner\run-sec-loop.ps1
```

The loop runs the wrapper in batches of 2 tickers and auto-restarts until D: free space <= 5.5 GiB.

### Option B: Single batch

```powershell
$env:SEC_USER_AGENT = "Stock-Data-Fetcher <your-real-email@example.com>"
python .\sec-runner\run-sec-backfill.py --max-tickers 10
```

## Monitoring

- Progress log: `D:\DEV\USTOCK\SEC\backfill-progress.log`
- Stdout log: `D:\DEV\USTOCK\SEC\backfill-stdout.log`
- Stderr log: `D:\DEV\USTOCK\SEC\backfill-stderr.log`

## Notes

- Do **not** commit `D:\SEC_WAREHOUSE`, downloaded SEC files, `tickers.txt`, `ticker-cik.json`, or your real email to GitHub.
- The runner skips tickers whose CIK has already been downloaded (share-class deduplication).
- If a ticker fails with exit code 2, rerun the same command; completed accessions are skipped automatically.
