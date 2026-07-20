# SEC Evidence Chain and Deterministic Parsing Contract

## Objective

The SEC layer is a governed source layer for later semantic extraction. It must answer four questions for
every downstream claim:

1. Which filing and acceptance timestamp made the information public?
2. Which SEC document, Item/section, table, or XML record supplied it?
3. Were the downloaded bytes identical to the recorded evidence SHA-256?
4. Can the parser reproduce the same IDs and normalized rows without an LLM?

## Contract

| Stage | Input | Deterministic output | Evidence retained |
|---|---|---|---|
| Raw intake | `filing.json`, evidence JSON, complete-submission bytes | `filings.csv` | accession, PIT acceptance time, source URL fields, SHA-256 verification |
| SGML split | `<DOCUMENT>` blocks | `documents.csv`, optional payload files | sequence, type, filename, byte range, block and payload SHA-256 |
| Type separation | filename, `<TYPE>`, wrapper and content signatures | HTML, Inline XBRL, XML, XBRL XML, binary attachment classes | classification and MIME type |
| Narrative split | primary 10-K/10-Q/8-K HTML | `sections.csv` | Part, Item, character range, section text SHA-256 |
| Table split | primary HTML `<table>` elements | `tables.csv` | source document ID, table index, section hint, normalized row matrix hash |
| XBRL parse | Inline XBRL and instance XML | `xbrl_facts.csv` | concept, context, unit, decimals, scale, sign, format, value |
| Ownership parse | Form 4 XML | `form4_transactions.csv` | owner/issuer identity, role, transaction details, 10b5-1 marker |
| Sale notice parse | Form 144 XML | `form144_notices.csv` | seller, relationship, broker, planned date, units and market value |
| Holdings parse | 13F information table XML | `form13f_holdings.csv` | CUSIP, issuer, class, value, units, discretion and voting authority |

## Point-in-time rule

`acceptanceDateTime` is the default information-availability timestamp. `reportDate`, fiscal period end,
transaction date, and planned-sale date describe the subject matter but do not replace the SEC acceptance
time in backtests or event studies.

## Amendments

`10-K/A`, `10-Q/A`, `8-K/A`, `4/A`, `144/A`, and `13F-HR/A` retain their original form in `form`, use the
base form in `base_form`, and set `is_amendment=1`. They are separate PIT events and must not overwrite the
original accession.

## Failure policy

- SHA mismatches are written as errors and the filing status becomes `evidence_mismatch`.
- Missing complete-submission files become `missing_raw`.
- Per-filing parser failures are recorded in `processing_issues.csv`; other filings continue unless
  `--fail-fast` is supplied.
- Unknown attachments remain separated and hashed rather than being silently discarded.

## Downstream semantic extraction

The deterministic layer intentionally stops before semantic inference. A later semantic system may extract
products, suppliers, customers, risks, regulatory events, and strategy relationships, but every assertion
should retain at minimum:

```text
filing_id
acceptance_datetime
document_id
section_id or table_id
source_sha256
text/table evidence
extractor version
assertion type: explicit | estimated | inferred | external
```

This separation prevents an LLM summary from becoming the source of record and allows GraphAlphaLab or any
other consumer to recompute theme labels, purity, relationship edges, and event features from stable source
artifacts.
