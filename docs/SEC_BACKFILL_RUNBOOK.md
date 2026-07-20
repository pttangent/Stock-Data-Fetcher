# SEC full-history backfill runbook

This CLI downloads SEC filing history **strictly one ticker at a time**. It is designed for local or self-hosted execution, not GitHub-hosted runners.

## What “full history” means

For each ticker/CIK, the CLI reads:

1. `data.sec.gov/submissions/CIK##########.json`;
2. the `filings.recent` column arrays;
3. every historical JSON shard named in `filings.files[]`;
4. every selected accession number, deduplicated across recent and historical shards.

SEC electronic indexes generally cover public EDGAR filings from 1994 Q3 onward. A company may have fewer records because it listed later, changed registrant, merged, or filed under another CIK.

## Download modes

- `complete`: one raw complete-submission `.txt` per accession. Recommended default for an evidence archive.
- `primary`: only the primary filing document.
- `both`: complete submission plus primary document.
- `none`: metadata inventory only.

The complete submission is preferred for evidence preservation because it contains the disseminated filing package and header in one file. The primary document is easier for later HTML parsing but may omit exhibits.

## Required setup

Use Node.js 22+ and pnpm. Set a real contact identity:

### PowerShell

```powershell
$env:SEC_USER_AGENT = "Stock-Data-Fetcher your-email@example.com"
```

### Bash

```bash
export SEC_USER_AGENT="Stock-Data-Fetcher your-email@example.com"
```

Do not run several instances against SEC at the same time. The CLI serializes requests and defaults to a 350 ms request gap.

## First: dry-run and space estimate

```powershell
pnpm install --frozen-lockfile
pnpm --filter @workspace/scripts sec:backfill -- `
  --ticker AAPL `
  --forms all `
  --documents complete `
  --dry-run `
  --output D:\SEC_WAREHOUSE
```

Read:

```text
D:\SEC_WAREHOUSE\ticker=AAPL\cik=0000320193\inventory.json
```

Important fields:

- `selectedFilings`
- `estimatedSubmissionSize`
- `sizeMetadataMissingCount`
- `recommendedFreeSize`

The estimate sums SEC filing `size` metadata, substitutes 512 KiB when size is missing, then adds headroom for manifests, partial files and filesystem overhead.

## Recommended production commands

### One ticker, all forms, complete submissions

```powershell
pnpm --filter @workspace/scripts sec:backfill -- `
  --ticker AAPL `
  --forms all `
  --documents complete `
  --output D:\SEC_WAREHOUSE
```

### One ticker, core issuer reports only

```powershell
pnpm --filter @workspace/scripts sec:backfill -- `
  --ticker AAPL `
  --forms core `
  --documents both `
  --output D:\SEC_WAREHOUSE
```

`core` means 10-K, 10-Q, 8-K, 20-F, 40-F and 6-K, including amendments unless `--no-amendments` is supplied.

### Multiple tickers, still strictly sequential

Create `tickers.txt`:

```text
AAPL
MSFT
NVDA
```

Then run:

```powershell
pnpm --filter @workspace/scripts sec:backfill -- `
  --ticker-file .\tickers.txt `
  --forms all `
  --documents complete `
  --output D:\SEC_WAREHOUSE
```

The script finishes one ticker before starting the next.

### Bypass online ticker mapping

This is useful when `company_tickers.json` is blocked or when a ticker has changed.

```powershell
pnpm --filter @workspace/scripts sec:backfill -- `
  --ticker AAPL `
  --cik 320193 `
  --forms all `
  --documents complete `
  --output D:\SEC_WAREHOUSE
```

For many symbols, provide a local mapping file:

```json
{
  "AAPL": "320193",
  "MSFT": "789019",
  "NVDA": "1045810"
}
```

```powershell
pnpm --filter @workspace/scripts sec:backfill -- `
  --ticker-file .\tickers.txt `
  --ticker-cik-file .\ticker-cik.json `
  --output D:\SEC_WAREHOUSE
```

## Resume and integrity behavior

- Files are written to `.part` paths and atomically renamed only after completion.
- Each downloaded file has an adjacent `.evidence.json` with source URL, fetch time, ETag, Last-Modified, byte size and SHA-256.
- Existing files with evidence are skipped on rerun.
- `--verify-existing` re-hashes existing files before skipping.
- Failed accessions are appended to `errors.jsonl`; other accessions and later tickers continue.
- Every run writes `_runs/<run-id>/run-manifest.json`, `ticker-results.jsonl` and `run-summary.json`.

## Output layout

```text
warehouse/sec/
├── _reference/
│   ├── company_tickers.json
│   └── submissions/CIK0000320193/
├── _runs/<run-id>/
└── ticker=AAPL/
    └── cik=0000320193/
        ├── company.json
        ├── inventory.json
        ├── run-summary.json
        ├── errors.jsonl
        └── accession=0000320193-26-000013/
            ├── filing.json
            ├── complete-submission.txt
            ├── complete-submission.txt.evidence.json
            ├── primary-document.htm
            └── primary-document.htm.evidence.json
```

## Space planning

Always trust the ticker-specific `inventory.json` dry-run estimate over generic rules. Practical planning ranges:

| Scope | Typical planning allowance per mature operating-company ticker |
|---|---:|
| Core forms, primary documents | 0.2–2 GB |
| Core forms, complete submissions | 0.5–5 GB |
| All forms, complete submissions | 2–20 GB |
| All forms, complete + primary | 3–30 GB |

These are planning ranges, not guarantees. Heavy 8-K exhibit users, foreign issuers with many 6-Ks, funds, financial institutions, active registration histories, or filers with many ownership reports can exceed them materially.

For a 5,000-ticker universe, do not pre-allocate by multiplying the high-end range blindly. First run metadata-only dry-runs in batches and sum `recommendedFreeBytes`. For a broad U.S. equity universe, begin with core forms rather than all forms unless ownership, registration and proxy filings are required.

Keep at least 20% free filesystem capacity beyond the generated recommendation, and avoid placing the archive inside the Git repository.

## Exit codes

- `0`: all selected tickers and files completed or were already present.
- `1`: startup/configuration failure.
- `2`: run completed but one or more tickers/files failed; rerun after resolving network or SEC access issues.
