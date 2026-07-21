# Local Agent Prompt Template — SEC Semantic Review Batch

Use this template only after the deterministic SEC pipeline and database validation have passed.

```text
You are performing a governed post-filing semantic review for the Equity Semantic Library.

Repository:
D:\DEV\AnotherNetworkFactory\SEC_Yfinance_Fetcher

Branch:
agent/equity-semantic-library-clean

Load and obey:
.agents/skills/sec-llm-semantic-review/SKILL.md
.agents/skills/sec-llm-semantic-review/references/PIT_POLICY.md
.agents/skills/sec-llm-semantic-review/references/FINANCIAL_SEMANTIC_POLICY.md
.agents/skills/sec-llm-semantic-review/references/REVIEW_OUTPUT_CONTRACT.md
.agents/skills/sec-llm-semantic-review/references/UPLOADED_ARCHIVE_CASEBOOK.md

Database:
D:\DEV\AnotherNetworkFactory\SEC_Yfinance_Fetcher\data\sec_yfinance_structured.db

Candidate SQL:
.agents/skills/sec-llm-semantic-review/assets/select_review_candidates.sql

Review scope:
- signal_timestamp: <ISO-8601 TIMESTAMP>
- run_id: <RUN_ID>
- batch_id: <BATCH_ID>
- candidate_reason: <ONE ALLOWED REASON>
- selection query hash: <SHA256>
- supplied assertion/relation/evidence IDs: <SCOPE>

Your job is not to summarize filings. Review only the selected deterministic assertions, relations, and stored evidence snippets.

For each record:
1. Verify primary evidence identity, source hash, and governed availability.
2. Reject evidence later than signal_timestamp.
3. Confirm that the record genuinely needs LLM review; otherwise return no_change.
4. Classify the statement as reported fact, management estimate, risk hypothesis, policy/rule, management interpretation, third-party statement, or reviewer inference.
5. Apply form-specific financial logic and the uploaded-archive casebook.
6. Choose exactly one action: accept, reject, supersede, create_candidate, no_change, taxonomy_candidate.
7. Use explicitness only as explicit, estimated, or inferred.
8. Preserve units, periods, scope, accounting basis, and actual/guidance status.
9. Never guess anonymous entities, infer relations from co-mention, turn 13F holdings into commercial relations, create issuer-side facts from another issuer's filing, or use future outcomes.
10. Produce one atomic claim per JSONL line.
11. Set status to review_required. Never write accepted facts directly to the database.
12. Record candidate_reason, model identity, prompt hash, taxonomy version, confidence, limitations, and all evidence IDs.

Do not browse the web or use external knowledge in this review batch.

Write output to:
data/sec_yfinance/reviews/<RUN_ID>/<BATCH_ID>.jsonl

Validate each record against:
.agents/skills/sec-llm-semantic-review/assets/llm_review_record.schema.json

Also write a batch manifest beside it.

Fail the batch rather than continue if evidence IDs are missing, source times differ from the database, future evidence is present, date-only evidence is used intraday, external enrichment is used, or any source evidence would need to be mutated.
```

## Suggested role split for large batches

Run independent reviewers in parallel, then use a separate challenger. Do not let the creator approve its own new assertion.

```text
product-lifecycle-reviewer
relation-role-reviewer
risk-and-realization-reviewer
event-decomposition-reviewer
segment-comparability-reviewer
contradiction-challenger
batch-governance-validator
```

Each reviewer receives only its assigned evidence rows and the frozen PIT boundary. The challenger receives proposed review records plus the same eligible evidence, but not future outcomes.

## Materiality routing

Require challenger review when any of these is true:

- relation names a supplier, customer, foundry, government, or competitor;
- claim changes a risk from hypothetical to realized;
- claim changes actual versus guidance classification;
- quantitative claim changes currency, unit, scale, segment, GAAP status, or period;
- disclosure delta is `removed`, `intensified`, or `de_intensified`;
- confidence is below 0.90;
- proposed taxonomy label would affect more than one issuer.

## First controlled batches

Run small company-specific batches before market-wide review:

```text
MU:
  HBM3E/HBM4 lifecycle states

AMD:
  MI308 actual/rule/risk decomposition
  TSMC foundry-role refinement
  segment-restatement comparability

AVGO:
  VCF ontology hierarchy
  anonymous customer concentration
  AI Revenue compensation metric versus actual revenue

NVDA:
  H20 estimate-to-actual PIT chain
  supply-chain role decomposition

GOOGL:
  antitrust-remedy decomposition

META:
  Llama strategy without monetization inference

AMZN:
  13F alias normalization only when identifiers are incomplete
```
