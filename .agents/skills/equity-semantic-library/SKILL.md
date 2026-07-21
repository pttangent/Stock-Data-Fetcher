---
name: equity-semantic-library
description: Build and validate a structured, point-in-time-safe public-equity source library using official SEC EDGAR metadata/filings, EdgarTools, yfinance and SQLite. Use for issuer identity, company profiles, annual filing collection, evidence sections, ingestion QA and later evidence-backed semantic extraction. Do not use to invent suppliers, customers or business facts without source evidence.
---

# Equity Semantic Library

## Required order

1. Read `README.md`, `docs/SCHEMA.md` and `docs/SOURCE_POLICY.md`.
2. Require `SEC_IDENTITY` with a real email before SEC access.
3. Initialize the database with `esl init`.
4. Process only the supplied manifest or symbol list.
5. Run `esl validate` before increasing batch size.

## Source responsibilities

- SEC is authoritative for CIK, issuer name, filing form, accession number and `available_at`.
- EdgarTools is the preferred filing text adapter.
- The official SEC archive is the fallback for filing content.
- yfinance is supplemental and never overwrites SEC identity.

## Hard rules

- Exact annual forms only: `10-K`, `20-F`, `40-F`.
- Do not treat amendments as base filings.
- Do not write placeholder strings such as `<NA>`, `nan`, `unknown` or `review_required` into factual fields.
- Preserve raw payloads, document hashes and exact evidence offsets.
- Use stable deterministic IDs and idempotent writes.
- Record every failed symbol in `ingestion_error` and the work queue.
- A Yahoo-only issuer remains provisional.
- Research use requires `available_at <= signal_timestamp`.
- Never infer supplier/customer relations during ingestion.

## Post-filing review routing

When deterministic extraction is complete but a product, relation, risk, event, disclosure delta, entity alias, or taxonomy label remains ambiguous, stop using this ingestion skill and load:

```text
.agents/skills/sec-llm-semantic-review/SKILL.md
```

That reviewer is append-only, evidence-ID-bound, PIT-gated, and is not authorized to rewrite source evidence or directly accept new database facts.

## Commands

```bash
esl --db data/equity_semantic.db init
esl --data-dir data bootstrap-sec --bulk-submissions
esl --db data/equity_semantic.db ingest AAPL MSFT
esl --db data/equity_semantic.db ingest-file symbols.csv --limit 100
esl --db data/equity_semantic.db validate --output reports/validation.json
pytest
```

## Completion gate

A batch is complete only when validation passes, no accepted source record contains placeholder nulls, foreign-key checks are clean, SEC documents have deterministic availability time, and a repeated run creates no duplicate source documents or sections.
