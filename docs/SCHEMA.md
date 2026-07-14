# Database schema

## Identity layer

`issuer` is the company/issuer entity. SEC-resolved issuers use the stable key `issuer:sec:<CIK>`. A Yahoo-only issuer is explicitly provisional.

`security` is a tradable symbol linked to an issuer. A share class, ADR, note, warrant or ETF can be represented as a distinct security without inventing a separate issuer.

## Source layer

`source_record` stores immutable API payload versions. A changed payload creates a new hash/version; an unchanged payload updates only `last_observed_at`.

`source_document` stores one SEC filing per accession number. It records filing date, acceptance time, report period, primary document, source URL, local path and content hash.

`filing_section` stores exact text with character offsets. This is the evidence anchor for future semantic facts.

## Normalized layer

`company_profile_snapshot` is a time-stamped yfinance snapshot. Its `sector_source` and `industry_source` fields are source labels, not a canonical taxonomy.

## Future semantic layer

`semantic_fact` and `company_relation` require evidence pointers. Explicit and inferred records are separated using `explicitness`; inferred relations must never be promoted to explicit without source evidence.

## Point-in-time rule

Research queries must enforce:

```sql
available_at <= :signal_timestamp
```

`effective_from/effective_to` are separate business-validity fields. They must not be fabricated to satisfy the knowledge-time condition.
