# Local Agent Prompt Template — SEC Semantic Review Batch

Use this template only after deterministic SEC parsing, structured extraction, and database validation pass.

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
.agents/skills/sec-llm-semantic-review/references/POTENTIAL_EVENT_POLICY.md
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

Your job is not to summarize filings. Review only selected deterministic assertions, relations, and stored evidence snippets.

For each record:
1. Verify primary evidence identity, source hash, and governed availability.
2. Reject evidence later than signal_timestamp.
3. Confirm that the record genuinely needs LLM review; otherwise return no_change.
4. Classify claim_class.
5. Classify occurrence_status exactly as one of:
   occurred, ongoing, announced_not_occurred, expected_not_occurred,
   conditional_potential, hypothetical_risk, undetermined, not_applicable.
6. When the event has not happened, use predicate = potential_event and preserve trigger conditions, expected window, probability language, and affected scope only when explicitly disclosed.
7. Never convert a potential event into an occurred fact because a later filing confirmed it.
8. When later evidence reports realization, create a new occurred record and link resolves_prior_review_id; preserve the earlier potential record unchanged.
9. Apply form-specific financial logic and the uploaded-archive casebook.
10. Choose exactly one action: accept, reject, supersede, create_candidate, no_change, taxonomy_candidate.
11. Use explicitness only as explicit, estimated, or inferred.
12. Preserve units, periods, scope, accounting basis, and actual/guidance status.
13. Never guess anonymous entities, infer relations from co-mention, turn 13F holdings into commercial relations, create issuer-side facts from another issuer's filing, or use future outcomes.
14. Produce one atomic claim per JSONL line.
15. Set status to review_required. Never write accepted facts directly to the database.
16. Record candidate_reason, model identity, prompt hash, taxonomy version, confidence, limitations, occurrence_status, and all evidence IDs.

Do not browse the web or use external knowledge in this review batch.

Write output to:
data/sec_yfinance/reviews/<RUN_ID>/<BATCH_ID>.jsonl

Validate every line against:
.agents/skills/sec-llm-semantic-review/assets/llm_review_record.schema.json

Also write a batch manifest beside it.

Fail the batch rather than continue if evidence IDs are missing, source times differ from the database, future evidence is present, date-only evidence is used intraday, external enrichment is used, occurrence_status is missing, a potential event is written as occurred, an occurred event is written as potential, or source evidence would need mutation.
```

## Suggested role split

```text
product-lifecycle-reviewer
potential-event-reviewer
relation-role-reviewer
risk-and-realization-reviewer
event-decomposition-reviewer
segment-comparability-reviewer
contradiction-challenger
batch-governance-validator
```

Each reviewer receives only assigned evidence and the frozen PIT boundary. The challenger sees proposed records plus the same eligible evidence, but never future outcomes.

## First controlled batches

```text
MU:
  HBM3E/HBM4 lifecycle states
  sampling occurred versus future production potential

AMD:
  MI308 charge occurred
  export licensing ongoing
  future China sales conditional potential
  TSMC foundry-role refinement
  segment-restatement comparability

AVGO:
  VCF ontology hierarchy
  anonymous customer concentration
  AI Revenue PSU target as conditional potential, not realized revenue

NVDA:
  H20 expected $5.5B charge as potential
  later $4.5B charge as occurred
  supply-chain role decomposition

GOOGL:
  antitrust decision occurred
  remedy obligations ongoing
  future implementation or financial effect potential only if stated

META:
  Llama strategy without monetization inference

AMZN:
  13F alias normalization only when identifiers are incomplete
```

## Mandatory challenger routing

Require a second reviewer when:

- relation names supplier, customer, foundry, government, or competitor;
- occurrence_status changes from future/potential to occurred;
- a later record resolves a prior potential event;
- actual versus guidance classification changes;
- currency, unit, scale, segment, GAAP status, or period changes;
- disclosure delta is removed, intensified, or de_intensified;
- confidence is below 0.90;
- taxonomy affects more than one issuer.
