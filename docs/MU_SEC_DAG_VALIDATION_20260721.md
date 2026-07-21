# MU SEC DAG validation — 2026-07-21

The uploaded `ticker=MU.zip` was processed end to end with the new form policy and multi-worker DAG.

## Scope

The archive contained 170 filings. Ownership reports were excluded:

- Form 4: 95
- Form 144 / 144-A: 40
- Form 3: 3
- Form 5: 2

Twenty-seven supported non-ownership filings entered the pipeline:

| Form | Filings |
|---|---:|
| 8-K | 13 |
| 10-Q | 3 |
| 10-K | 1 |
| DEF 14A | 1 |
| PRE 14A | 1 |
| DEFA14A | 1 |
| SD | 1 |
| 424B2 | 2 |
| 424B5 | 2 |
| FWP | 2 |

## Result

- DAG tasks: 54/54 completed
- Filing status: 27/27 `structured`
- Filing documents/attachments indexed: 855
- Item/section chunks: 170
- HTML tables: 716
- key XBRL facts: 450
- 8-K event ledger rows: 29
- short PIT evidence snippets: 521
- deterministic semantic assertions: 521
- pipeline issues: 0
- ownership forms in DB: 0
- SHA-256 mismatches: 0
- missing filing/evidence availability times: 0
- orphan assertions: 0
- SQLite `PRAGMA quick_check`: `ok`

Wall-clock time in the validation container was about 19.5 seconds with separate core, event, other-form and semantic worker lanes. This is a format and governance validation, not a hardware benchmark for the user's Windows workstation.

A first pass exposed self-referential company-name relation candidates (Micron being interpreted as a Micron counterparty). The strict relation extractor was corrected to reject relations whose target ticker equals the filing issuer. After the correction, the MU run produced zero unsupported company relations rather than retaining a false positive.
