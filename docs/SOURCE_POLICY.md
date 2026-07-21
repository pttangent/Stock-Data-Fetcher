# Source policy

## Authority order

1. SEC submissions JSON and filing archive
2. EdgarTools representation of the same SEC records
3. Official issuer investor-relations documents (future extension)
4. yfinance supplemental metadata

SEC controls CIK, issuer identity, filing form, accession number and point-in-time availability. yfinance may fill profile attributes but may not overwrite SEC identity.

## Annual forms

Supported base annual reports are exact `10-K`, `20-F` and `40-F`. The collector chooses the most recent exact base filing available for the issuer. Amendments (`10-K/A`, `20-F/A`, `40-F/A`) are separate documents and are not substitutes for the base filing.

## Failure policy

- Empty or malformed responses are errors.
- A missing SEC mapping plus successful Yahoo profile produces a provisional issuer and `review_required` queue status.
- Partial success is preserved; one provider failure does not discard the other provider's valid data.
- All failures are written to `ingestion_error` with stage, source and retryability.


## Cache policy

- SEC ticker/submissions JSON is reused for 6 hours by default.
- yfinance profiles are reused for 24 hours by default.
- `--refresh` bypasses fresh caches.
- Cache reuse does not change original observation or SEC availability timestamps.
