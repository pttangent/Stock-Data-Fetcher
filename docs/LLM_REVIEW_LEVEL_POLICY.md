# LLM review policy for B and below

The semantic pipeline keeps deterministic promotion levels and uses the LLM as a governed reviewer rather than a free-form extractor.

## Default policy

```text
A: structured facts; excluded from the default LLM queue
B: deterministic accepted semantics; reviewed by LLM without blocking structure ingestion
C: unresolved contextual semantics; reviewed before formal promotion
D: lexical/form-policy evidence; reviewed before formal promotion
R: deterministic rejection; available for review/audit but never silently promoted
```

`review-export` now defaults to levels `B,C,D,R` and candidate statuses `rule_accepted,review_required,rejected`. Candidates that already have a `semantic_review` row are omitted unless `--include-reviewed` is supplied.

## Evidence grouping

Multiple candidates generated from the same evidence snippet are exported as one JSONL review unit. The unit contains a `candidates` array and the LLM must return one decision row per `candidate_id`.

This reduces repeated context while preserving candidate-level auditability. Use `--no-dedupe-evidence` to return one export unit per candidate.

## Export examples

Default B-and-below queue:

```powershell
esl-sec --config config/sec_pipeline.batch.json `
  --db data/batches/batch_01/sec_yfinance_structured.db `
  review-export `
  --output data/batches/batch_01/review_queue.jsonl
```

Only C and D:

```powershell
esl-sec --config config/sec_pipeline.batch.json `
  --db data/batches/batch_01/sec_yfinance_structured.db `
  review-export `
  --level C --level D `
  --output data/batches/batch_01/review_queue_cd.jsonl
```

Include A for a temporary quality audit:

```powershell
esl-sec --config config/sec_pipeline.batch.json `
  --db data/batches/batch_01/sec_yfinance_structured.db `
  review-export `
  --level A --level B --level C --level D --level R `
  --output data/batches/batch_01/review_queue_all.jsonl
```

## Review decision format

The exported review unit contains an array, but the decision file remains one JSON object per candidate:

```json
{"candidate_id":"candidate:...","decision":"accept","rationale":"The evidence supports the issuer-scoped semantic claim."}
```

```json
{"candidate_id":"candidate:...","decision":"reject","rationale":"The phrase is legal or third-party context and does not describe the issuer."}
```

```json
{"candidate_id":"candidate:...","decision":"change","corrected_predicate":"has_company_relation","corrected_object":{"target_entity":"Example Corp","target_ticker":"EXM","relation_type":"competitor"},"rationale":"The issuer explicitly identifies Example Corp as a competitor."}
```

## Governance of already accepted B candidates

B candidates already have deterministic outputs. LLM review applies the following rules:

- `accept`: confirms the existing assertion/relation and records a review-linked confirmation; it does not create a duplicate assertion.
- `reject`: marks the candidate rejected and supersedes its existing accepted assertion/relation.
- `change`: supersedes the old output and creates a corrected review-promoted output.
- `ambiguous`: records the review without silently changing the existing output.

All original evidence, PIT timestamps and deterministic promotion records remain preserved.

## Import

```powershell
esl-sec --config config/sec_pipeline.batch.json `
  --db data/batches/batch_01/sec_yfinance_structured.db `
  review-import `
  --input data/batches/batch_01/review_decisions.jsonl `
  --reviewer-type llm `
  --reviewer-id local-finance-reviewer `
  --reviewer-version model-version
```

The importer still rejects self-target relations, negative/non-actual relations presented as actual facts, and relation targets absent from the evidence snippet.

## Cross-industry sample scale

Across the 19 supplied databases, candidate levels were:

| Level | Rows |
|---|---:|
| A | 1,750 |
| B | 3,227 |
| C | 752 |
| D | 2,196 |
| B/C/D total | 6,175 |

Grouping by filing and `snippet_hash` reduced the B/C/D workload to about 3,713 evidence review units, roughly a 40% reduction without removing candidate-level decisions.
