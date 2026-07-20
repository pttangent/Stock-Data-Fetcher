# SEC evidence-chain support

## What this adds

The `SEC_EVIDENCE_CHAIN` tab queries SEC EDGAR from the server and returns:

- ticker-to-CIK resolution from the SEC ticker association file;
- filing metadata from `data.sec.gov/submissions/CIK##########.json`;
- official filing index and primary-document URLs;
- SEC `acceptanceDateTime` as the earliest official availability timestamp;
- local `fetchedAt` timestamps, response metadata, and optional SHA-256 hashes;
- a short text excerpt from the latest fetched filing document;
- a Yahoo Finance observation card for convenience, clearly separated from SEC evidence.

## Required configuration

SEC automated requests must identify the application and a real contact address. Configure the API server environment before starting it:

```bash
SEC_USER_AGENT="Stock-Data-Fetcher your-email@example.com"
```

The endpoint refuses to call SEC when this variable is missing or does not contain an email address. Do not hard-code a personal address in source control.

## Endpoint

```text
GET /api/sec/filings?symbol=AAPL&forms=10-K,10-Q,8-K&limit=20&includeDocument=true&documentLimit=1
```

Supported query parameters:

- `symbol`: ticker or a numeric CIK;
- `forms`: comma-separated forms;
- `limit`: 1–50 filing rows;
- `includeAmendments`: include `/A` amendments, default `true`;
- `includeDocument`: fetch and hash primary filing documents, default `false`;
- `documentLimit`: number of documents to fetch, 1–3.

## Evidence semantics

Use the fields as follows:

1. `acceptanceDateTime`: SEC dissemination/availability timestamp for point-in-time research.
2. `filingDate` and `reportDate`: legal filing date and covered reporting period; neither should replace availability time.
3. `fetchedAt`: when this application observed the source.
4. `accessionNumber` and official URLs: immutable document identity and replay path.
5. `sha256`: content fingerprint for the exact bytes observed by this application.

Yahoo Finance data is an observation source, not an archival evidence source. Its market timestamp plus local `fetchedAt` can document what was observed during a run, but historical point-in-time reconstruction requires persisting every raw response or using a licensed archival feed.

## Reliability controls

- server-side SEC access because `data.sec.gov` does not support browser CORS;
- mandatory descriptive user agent;
- serialized requests with a conservative delay below the SEC limit;
- retry with exponential backoff for 403, 429, and 5xx responses;
- request timeout and in-memory TTL cache;
- bounded filing count, document count, and document size;
- no hard-coded local paths or credentials.
