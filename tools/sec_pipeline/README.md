# SEC Evidence-Chain Pipeline

A deterministic, dependency-free parser for the SEC warehouse layout produced by Stock-Data-Fetcher.
It consumes either `ticker=*.zip` archives or extracted directories and turns each SEC complete-submission
file into auditable, normalized tables.

## Processing flow

```text
SEC raw filing
  -> deterministic SGML document split
  -> form recognition (10-K, 10-Q, 8-K, Form 4, Form 144, 13F-HR)
  -> HTML / Inline XBRL / XML / binary attachment separation
  -> Item / Part / section / HTML-table extraction
  -> rule-based structured parsers
  -> CSV tables + split documents + manifest + evidence hashes
```

No LLM is used. Every filing, document, section, table, XBRL fact, and structured row carries stable IDs and
links back to ticker, CIK, accession, acceptance time, source SHA-256, document SHA-256, and byte offsets.

## Run

From the repository root:

```bash
pnpm --filter @workspace/scripts sec:parse -- \
  --input "D:/SEC_WAREHOUSE/ticker=NVDA.zip" \
  --input "D:/SEC_WAREHOUSE/ticker=AMD.zip" \
  --output "D:/SEC_PARSED" \
  --document-mode all \
  --overwrite
```

The command uses `python`, then `python3`. Set `SEC_PYTHON` when a specific interpreter is required.
The parser itself uses only the Python standard library.

Filter forms or tickers:

```bash
pnpm --filter @workspace/scripts sec:parse -- \
  --input "D:/SEC_WAREHOUSE" \
  --output "D:/SEC_PARSED_CORE" \
  --forms "10-K,10-Q,8-K,4,144,13F-HR" \
  --tickers "NVDA,AMD,MU" \
  --document-mode primary \
  --overwrite
```

`--document-mode all` materializes every separated attachment. `primary` keeps only the primary filing
document. `none` emits tables and hashes without materializing document payloads.

## Output tables

| Table | Purpose |
|---|---|
| `filings.csv` | PIT filing metadata, source hash verification, and per-filing counts |
| `documents.csv` | Every SGML document/attachment, classification, byte range, and payload hash |
| `sections.csv` | 10-K/10-Q/8-K Item and Part text chunks |
| `tables.csv` | Deterministically extracted HTML tables as JSON row matrices |
| `xbrl_facts.csv` | Inline XBRL and instance XBRL facts |
| `form4_transactions.csv` | Insider transactions, owner role, 10b5-1 flag, prices, shares, ownership |
| `form144_notices.csv` | Planned-sale notices, seller, broker, sale date, units and market value |
| `form13f_holdings.csv` | 13F information-table holdings and voting authority |
| `processing_issues.csv` | Evidence mismatches and parse failures without silently dropping filings |

The `documents/` tree mirrors ticker/CIK/accession and contains the separated payloads. `manifest.json`
records parser/schema versions, inputs, filters, document mode, and table row counts.

`sections.csv` and `tables.csv` may contain very large text fields. Python consumers using the standard
`csv` module should call `csv.field_size_limit(sys.maxsize)` before reading them. DuckDB, Polars, or a later
Parquet conversion is preferable for large research runs.

## Tests

```bash
cd tools/sec_pipeline
python -m unittest -v test_sec_pipeline.py
```

## Deliberate boundaries

This layer performs document governance and deterministic extraction only. It does **not** infer suppliers,
customers, products, risks, themes, or sentiment. Those semantic layers should consume `sections.csv`,
`tables.csv`, and structured form tables while preserving the IDs and evidence fields emitted here.
