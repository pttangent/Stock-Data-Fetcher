# Equity Semantic Library

A clean, resumable ingestion repository for building a point-in-time-safe public-equity information library from:

- **SEC EDGAR**: authoritative issuer identity, CIK, filing metadata, annual filings, acceptance time and filing sections.
- **EdgarTools**: preferred filing-object/text adapter, following the referenced SEC skill workflow.
- **yfinance**: supplemental market/company profile snapshots. It never overwrites SEC identity.
- **SQLite**: portable, transactional, foreign-keyed and idempotent structured storage.

This repository does not ask an LLM to invent business segments, suppliers or customers. It first builds an auditable source and candidate layer, promotes only strict issuer-scoped facts, and optionally sends ambiguous short evidence to a review channel.

## Reliability rules

1. SEC identity is required and must contain a real contact email.
2. SEC traffic is kept below the SEC ceiling through a process-wide request-start gate shared by all download workers.
3. `available_at` comes from SEC `acceptanceDateTime`, falling back to `filingDate` with recorded date precision.
4. yfinance is supplemental observation data and never overwrites SEC CIK or legal identity.
5. Every write uses stable IDs/upserts. Re-running the same source payload does not duplicate records.
6. Raw SEC complete submissions are retained outside Git, compressed, hashed and linked to structured rows.
7. Short evidence retains source SHA-256, SEC acceptance time, local observation time and extractor version.
8. Keyword evidence enters `semantic_candidate`; only A/B-level structured or issuer-bound results enter accepted assertions automatically.
9. LLM or human review appends an immutable decision and never overwrites evidence or PIT timestamps.

## Install

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev,parquet]"
cp .env.example .env
```

Export the SEC identity in your shell:

```bash
export SEC_IDENTITY="Your Name your.email@example.com"
```

## Original single-symbol library

```bash
esl --db data/equity_semantic.db init
esl --data-dir data bootstrap-sec --bulk-submissions
esl --db data/equity_semantic.db ingest AAPL MSFT BRK.B
esl --db data/equity_semantic.db validate --output reports/validation.json
```

Core tables include `issuer`, `security`, `source_record`, `company_profile_snapshot`, `source_document`, `filing_section`, `ingestion_error`, `work_queue`, `ingestion_run`, `semantic_fact`, and `company_relation`.

See [docs/SCHEMA.md](docs/SCHEMA.md) and [docs/SOURCE_POLICY.md](docs/SOURCE_POLICY.md).

## Multi-worker SEC/Yfinance pipeline

The integrated production pipeline is a separate database and data tree. It reads local metadata without modifying it, schedules companies by descending market capitalization, and dynamically creates accession-level tasks:

```text
discover/download -> form-specific parse -> form-aware evidence/candidate extraction -> strict promotion
```

Forms 3, 4, 5 and 144 are excluded by default. Separate worker lanes handle annual/quarterly filings, 8-K events, 13F holdings, proxy/regulatory/offering documents, semantic extraction, Yahoo observations and finalization. Multiple SEC workers share one global rate gate.

Download only, so structure code can change while raw evidence continues to arrive:

```powershell
esl-sec --config .\config\sec_pipeline.batch.json `
  --db .\data\batches\batch_01\sec_yfinance_structured.db `
  --data-dir .\data\batches\batch_01 `
  run --mode download --metadata .\data\batches\batch_01.parquet
```

Offline structure and semantic processing using the downloaded raw files:

```powershell
esl-sec --config .\config\sec_pipeline.batch.json `
  --db .\data\batches\batch_01\sec_yfinance_structured.db `
  --data-dir .\data\batches\batch_01\sec_yfinance `
  run --mode structure --metadata .\data\batches\batch_01.parquet
```

Rebuild only the derived semantic layer after changing promotion rules:

```powershell
esl-sec --config .\config\sec_pipeline.batch.json `
  --db .\data\batches\batch_01\sec_yfinance_structured.db `
  --data-dir .\data\batches\batch_01\sec_yfinance `
  run --mode structure --rebuild-semantic `
  --metadata .\data\batches\batch_01.parquet
```

Offline MU/archive replay:

```powershell
esl-sec --config .\config\sec_pipeline.local.json import-archive `
  "D:\PATH\TO\ticker=MU.zip"
```

## Candidate review channel

Export only ambiguous candidates with their short evidence and immutable PIT fields:

```powershell
esl-sec --config .\config\sec_pipeline.batch.json `
  --db .\data\batches\batch_01\sec_yfinance_structured.db `
  review-export --output .\data\batches\batch_01\review_queue.jsonl
```

Import append-only human or LLM decisions:

```powershell
esl-sec --config .\config\sec_pipeline.batch.json `
  --db .\data\batches\batch_01\sec_yfinance_structured.db `
  review-import --input .\data\batches\batch_01\review_decisions.jsonl `
  --reviewer-type llm --reviewer-id local-finance-reviewer `
  --reviewer-version model-or-skill-version
```

The reviewer may accept, reject or correct a candidate, but cannot replace evidence, change `available_at`, promote self-target/non-actual relations, or add a relation target absent from the evidence.

Monitor and resume:

```powershell
esl-sec --config .\config\sec_pipeline.local.json status <RUN_ID>
esl-sec --config .\config\sec_pipeline.local.json resume <RUN_ID>
esl-sec --config .\config\sec_pipeline.local.json validate --output .\reports\validation.json
```

Read [docs/SEC_YFINANCE_DAG_PIPELINE.md](docs/SEC_YFINANCE_DAG_PIPELINE.md), [docs/SEC_SEMANTIC_PROMOTION_AND_REVIEW.md](docs/SEC_SEMANTIC_PROMOTION_AND_REVIEW.md), [docs/MU_SEC_DAG_VALIDATION_20260721.md](docs/MU_SEC_DAG_VALIDATION_20260721.md), and [LOCAL_AGENT_FULL_PIPELINE.md](LOCAL_AGENT_FULL_PIPELINE.md).

## Tests

Unit tests are offline and use synthetic SEC/Yahoo responses:

```bash
pytest
python -m compileall -q src
```

Live network tests should be opt-in and marked `integration`.

## Upstream references

- SEC EDGAR APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC fair-access guidance: https://www.sec.gov/about/developer-resources
- yfinance documentation: https://ranaroussi.github.io/yfinance/
- Referenced EdgarTools skill: https://skillsmp.com/creators/hkuds/vibe-trading/agent-src-skills-edgar-sec-filings
