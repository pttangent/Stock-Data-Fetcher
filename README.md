# Equity Semantic Library

A clean, resumable ingestion repository for building a point-in-time-safe public-equity information library from:

- **SEC EDGAR**: authoritative issuer identity, CIK, filing metadata, annual filings, acceptance time and filing sections.
- **EdgarTools**: preferred filing-object/text adapter, following the referenced SEC skill workflow.
- **yfinance**: supplemental market/company profile snapshots. It never overwrites SEC identity.
- **SQLite**: portable, transactional, foreign-keyed and idempotent structured storage.

This repository intentionally does **not** ask an LLM to invent business segments, suppliers or customers. It first builds the auditable source layer required for later semantic extraction.

## Reliability rules

1. SEC identity is required and must contain a real contact email.
2. SEC traffic defaults to 5 requests/second, below the SEC's published 10 requests/second ceiling.
3. Annual filing selection accepts only exact `10-K`, `20-F` and `40-F`, then chooses the most recent base annual report; amendments are never promoted as the base filing.
4. EdgarTools is attempted first for filing text; the official SEC archive is the deterministic fallback.
5. `available_at` comes from SEC `acceptanceDateTime`, falling back to `filingDate` with recorded date precision.
6. yfinance is sequential, cached for 24 hours by default and retried. Empty responses are errors, never accepted records.
7. Every write uses stable IDs/upserts. Re-running the same source payload does not duplicate records.
8. Raw source payloads and filing text are retained outside Git and linked by hashes.

## Install

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev,parquet]"
cp .env.example .env
```

Export the SEC identity in your shell (or load `.env` using your preferred environment manager):

```bash
export SEC_IDENTITY="Your Name your.email@example.com"
```

## Quick start

```bash
# Initialize
esl --db data/equity_semantic.db init

# Optional: preload SEC ticker map and nightly submissions archive for large universes
esl --data-dir data bootstrap-sec --bulk-submissions

# Ingest symbols using SEC + yfinance
esl --db data/equity_semantic.db ingest AAPL MSFT BRK.B

# Ignore fresh caches and fetch again
esl --db data/equity_semantic.db ingest AAPL --refresh

# Ingest the first 100 rows from CSV/Parquet
esl --db data/equity_semantic.db ingest-file symbol_metadata.parquet \
  --symbol-column symbol --limit 100

# Validate and export
esl --db data/equity_semantic.db validate --output reports/validation.json
esl --db data/equity_semantic.db export security reports/security.csv
```

For Yahoo-only development (records remain provisional and validation will not release the run):

```bash
esl ingest AAPL --no-sec
```

## Structured output

Core tables:

- `issuer`: stable issuer identity, using `issuer:sec:<10-digit CIK>` when available.
- `security`: symbol-level security linked to an issuer.
- `source_record`: immutable raw API snapshots with hashes and observation time.
- `company_profile_snapshot`: normalized yfinance fields plus untouched raw JSON.
- `source_document`: one row per SEC accession number.
- `filing_section`: exact filing text chunks with offsets and hashes.
- `ingestion_error`: retryable/non-retryable failure audit trail.
- `work_queue` and `ingestion_run`: resumable run state.
- `semantic_fact` and `company_relation`: evidence-backed extension tables for later L1–L5 processing.

See [docs/SCHEMA.md](docs/SCHEMA.md) and [docs/SOURCE_POLICY.md](docs/SOURCE_POLICY.md).

## Tests

Unit tests are offline and use fake SEC/Yahoo responses:

```bash
pytest
```

Live network tests should be opt-in and marked `integration`.

## Upstream references

- SEC EDGAR APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC fair-access guidance: https://www.sec.gov/about/developer-resources
- yfinance documentation: https://ranaroussi.github.io/yfinance/
- Referenced EdgarTools skill: https://skillsmp.com/creators/hkuds/vibe-trading/agent-src-skills-edgar-sec-filings
