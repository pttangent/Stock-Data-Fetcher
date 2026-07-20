# SEC parser validation — 2026-07-21

## Scope

The deterministic parser was exercised against locally supplied SEC evidence archives for:

- AMD
- AMZN
- AVGO
- GOOGL
- META
- MU
- NVDA

No uploaded SEC payloads or generated research tables were committed to the repository.

## Unit validation

Command:

```bash
cd tools/sec_pipeline
python -W error::DeprecationWarning -m unittest -v test_sec_pipeline.py
python -m py_compile sec_pipeline.py
```

Result: six tests passed. Coverage includes SGML document splitting, body-versus-TOC Item selection,
HTML table extraction, Inline XBRL facts, Form 4, Form 144, 13F information tables, stable IDs, evidence
hash verification, and an end-to-end ZIP archive run.

## Real-filing smoke validation

A form-stratified sample of 38 real filings was selected across the seven issuers. The sample covered:

| Base form | Filings |
|---|---:|
| 10-K | 7 |
| 10-Q | 7 |
| 8-K | 7 |
| Form 4 | 7 |
| Form 144 | 7 |
| 13F-HR | 3 |

Produced rows:

| Output | Rows |
|---|---:|
| filings | 38 |
| separated documents | 1,646 |
| Item/section chunks | 242 |
| HTML tables | 1,079 |
| XBRL facts | 27,277 |
| Form 4 transactions | 16 |
| Form 144 notices | 7 |
| 13F holdings | 58 |
| processing issues | 0 |

All 38 complete-submission files matched their recorded SHA-256 evidence. All 38 filing statuses were
`complete` in the smoke output.

## Interpretation

This validation establishes format coverage and deterministic extraction for the supplied issuer samples.
It does not claim universal EDGAR compatibility. Unknown attachment types remain separated and hashed, and
future schema variants must surface through `processing_issues.csv` rather than being silently ignored.
