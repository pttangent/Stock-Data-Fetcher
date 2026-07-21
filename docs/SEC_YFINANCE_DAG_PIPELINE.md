# SEC/Yfinance multi-worker DAG pipeline

## Purpose

This pipeline turns a read-only symbol universe into a separate, point-in-time-safe SQLite evidence and semantic database. It does not modify `symbol_metadata.parquet`, and it does not place downloaded SEC payloads inside the Git repository.

```text
symbol_metadata.parquet (read only)
  -> market-cap descending symbol queue
  -> shared-rate-gated SEC discovery/download workers
  -> form-specific parsing workers
  -> form-specific deterministic semantic workers
  -> short PIT evidence + structured SQLite tables
  -> optional LLM review/correction layer
```

## Form policy

Ownership reports are excluded by default because they are numerous and are not required for the first semantic library: Forms 3, 4, 5, 144 and their amendments.

| Form family | Parse worker | Semantic output |
|---|---|---|
| 10-K / 20-F / 40-F | `parse_core` | business, products, supply chain, competitors, risks, key XBRL facts |
| 10-Q | `parse_core` | quarterly operations, updated risks, MD&A, key XBRL facts |
| 8-K / 6-K | `parse_event` | PIT event ledger by Item code |
| 13F-HR | `parse_holdings` | structured holdings and explicit investment relations |
| DEF/PRE/DEFA 14A/14C | `parse_other` | proposals, director election, compensation, auditor, related-party topics |
| SD / CORRESP / UPLOAD | `parse_other` | conflict-minerals and SEC comment/response evidence |
| S-1/S-3/S-4/424B*/FWP | `parse_other` | securities, use of proceeds, dilution and distribution topics |

## Concurrency and SEC fairness

Several download workers may be active, but every SEC request passes through one process-wide `GlobalRateGate`. The default starts requests no faster than four per second. Network waits can overlap; request starts remain paced.

Processing does not wait for a ticker to finish. As soon as one accession is downloaded, its form-specific parse task becomes ready. Its semantic task depends on that parse task. SQLite WAL, task leases and dependency rows make the DAG resumable.

## Database governance

The new database is separate from the source metadata and the older Equity Semantic Library DB. It includes:

- `symbol_universe`: copied scheduling fields plus source path and immutable row hash;
- `filing`: accession, form, SEC acceptance time, source URL, original SHA-256 and storage URI;
- `filing_document`, `filing_section`, `filing_table`, `xbrl_fact`;
- `form13f_holding`, `event_ledger`;
- `semantic_assertion`, `company_relation`;
- `evidence_snippet`: short source evidence, source SHA-256, `accepted_at`, `available_at`, local `observed_at`, offsets and extractor version;
- `dag_task`, `dag_dependency`, `dag_event`, `pipeline_issue`.

`available_at` is SEC `acceptanceDateTime`; filing date is used only as a recorded date-precision fallback. yfinance snapshots use their local observation time and never overwrite SEC identity.

## Space policy

Only one compressed complete submission is retained per accession. The parser records every embedded document and its hashes without materializing each attachment by default. Tables are bounded row matrices; their full row/column counts and hashes remain available. Key XBRL mode stores finance-relevant concepts instead of every presentation fact.

## Commands

```powershell
$env:SEC_IDENTITY = "Stock-Data-Fetcher your-real-email@example.com"

esl-sec --config .\config\sec_pipeline.example.json init
esl-sec --config .\config\sec_pipeline.example.json run
esl-sec --config .\config\sec_pipeline.example.json status <RUN_ID>
esl-sec --config .\config\sec_pipeline.example.json resume <RUN_ID>
esl-sec --config .\config\sec_pipeline.example.json validate --output .\reports\sec-validation.json
```

Offline validation or reprocessing of existing archives does not require SEC identity:

```powershell
esl-sec --config .\config\sec_pipeline.example.json import-archive `
  "D:\SEC_WAREHOUSE\ticker=MU.zip"
```

## LLM correction contract

LLM output must never replace evidence. A later reviewer may change an assertion's status or add a superseding assertion, but must reference `evidence_id`, preserve original `available_at`, and record a reviewer/model/version. Deterministic accepted assertions remain immutable audit records.
