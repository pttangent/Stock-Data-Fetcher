# SEC semantic promotion and post-LLM review

The structure pipeline separates four objects:

```text
immutable short evidence
  -> high-recall semantic candidate
  -> deterministic promotion gate
  -> accepted assertion / company relation
  -> optional human or LLM review for remaining candidates
```

## Why this is required

A keyword hit is not the same thing as an issuer fact. Examples that must remain review candidates instead of accepted facts include:

- `subscription` in a securities offering;
- Google Cloud in a director biography filed by another issuer;
- Intel and the word `customer` in an AMD sentence whose grammatical subject is Intel;
- a geography name that appears only as a currency or legal address.

The pipeline still keeps the short evidence and PIT timestamps. It reduces automatic promotion, not evidence recall.

## Deterministic levels

| Level | Meaning | Default destination |
|---|---|---|
| A | structured SEC fact, such as 8-K Item or 13F row | accepted assertion |
| B | issuer-scoped statement with form/section policy and strict binding | accepted assertion |
| C | plausible contextual interpretation or unresolved subject | review queue |
| D | lexical/co-occurrence evidence or disallowed form context | review queue |
| R | self-target or structurally invalid relation | rejected candidate |

Every accepted deterministic assertion has a row in `candidate_promotion`. Every assertion retains its original `evidence_id` and `available_at`.

## Form and section policy

`section_semantic_context` records the role assigned to each section. Generic topic and concept rules are promoted only in compatible issuer sections:

- annual business section: business, technology, product and end-market topics;
- Item 1A / risk section: risk topics;
- MD&A / financial context: finance topics;
- 8-K: Item-code events are the primary accepted semantics;
- 13F: structured holdings are accepted;
- Proxy: only governance whitelist rules are accepted;
- Offering: only capital-markets whitelist rules are accepted;
- CORRESP / SD: only regulatory whitelist rules are accepted.

All other keyword evidence remains in `semantic_candidate` with `review_required` status.

## Company relations

Automatic company relations require all of the following:

1. the section is issuer-scoped;
2. a strict first-person relation phrase is present, such as `we rely on`, `our suppliers include`, or `we compete with`;
3. the target entity occurs after the relation phrase and within the bounded argument window;
4. polarity is positive and modality is actual;
5. the target does not resolve to the filing issuer.

Loose co-occurrence is retained only as a candidate. It never enters `company_relation` automatically.

## GOOG / GOOGL and other multi-class issuers

SEC facts are stored once under `issuer_id`. Views expose issuer facts through every security class:

- `security_filing`;
- `security_semantic_assertion`;
- `security_company_relation`;
- `security_event_ledger`.

This avoids duplicating Alphabet assertions while allowing both GOOG and GOOGL queries to return the same issuer-level facts. A future class-specific assertion may still set `security_id`; ordinary issuer facts use `security_id = NULL`.

## Rebuilding local semantics without SEC network access

To rebuild semantics after changing rules while retaining downloaded raw filings:

```powershell
esl-sec --config config/sec_pipeline.batch.json `
  --db data/batches/batch_01/sec_yfinance_structured.db `
  --data-dir data/batches/batch_01/sec_yfinance `
  run --mode structure --rebuild-semantic `
  --metadata data/batches/batch_01.parquet
```

`downloaded` filings are parsed and structured. `parsed` filings run semantic workers directly. With `--rebuild-semantic`, already `structured` filings have only their derived semantic layer cleared and regenerated; raw files, parsed sections, tables and XBRL remain available. Historical `semantic_review` rows are retained as an audit trail.

## Exporting the LLM review queue

```powershell
esl-sec --config config/sec_pipeline.batch.json `
  --db data/batches/batch_01/sec_yfinance_structured.db `
  review-export --output data/batches/batch_01/review_queue.jsonl
```

Each JSONL row contains:

- candidate and candidate ID;
- issuer and all mapped symbols;
- form, Item, section role and accession;
- short evidence, evidence hash and SEC source hash;
- `accepted_at`, `available_at` and `observed_at`;
- a machine-readable output contract.

The reviewer must not change candidate ID, evidence ID or PIT time, and must not introduce an entity absent from the evidence.

## Importing decisions

A decision JSONL row has this shape:

```json
{
  "candidate_id": "...",
  "decision": "accept",
  "rationale": "The issuer is the subject and the evidence supports the topic."
}
```

For a correction:

```json
{
  "candidate_id": "...",
  "decision": "change",
  "corrected_predicate": "has_topic",
  "corrected_object": {"topic": "cloud_services", "group": "end_market"},
  "rationale": "The evidence concerns the issuer's cloud operations, not a third-party biography."
}
```

Import:

```powershell
esl-sec --config config/sec_pipeline.batch.json `
  --db data/batches/batch_01/sec_yfinance_structured.db `
  review-import --input data/batches/batch_01/review_decisions.jsonl `
  --reviewer-type llm --reviewer-id local-finance-reviewer `
  --reviewer-version model-or-skill-version
```

The importer appends an immutable `semantic_review` record. Accepted or changed decisions create a new accepted assertion linked through `candidate_promotion`; they never overwrite evidence. Rejected candidates remain auditable. LLM decisions cannot promote self-target relations, non-actual relations, or relation targets absent from the evidence snippet.
